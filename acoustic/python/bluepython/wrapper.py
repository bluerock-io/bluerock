# Copyright (C) 2025 BlueRock Security, Inc.
# All rights reserved.

import inspect
import time
from collections import defaultdict
import threading
import wrapt
from . import backend
from . import cfg


class Measurement:
    __slots__ = ("_duration", "_max", "_min", "_count")

    def __init__(self):
        self._duration = 0.0
        self._max = 0.0
        self._min = float("inf")
        self._count = 0

    def process(self, duration):
        self._duration += duration
        self._max = max(duration, self._max)
        self._min = min(duration, self._min)
        self._count += 1


Cumulative = defaultdict(Measurement)
Lock = threading.Lock()


def measure_time(fn):
    if not fn or not cfg.sensor_config.profiling:
        return fn

    def profile_wrapper(*args, **kwargs):
        start_time = time.monotonic()
        try:
            return fn(*args, **kwargs)
        finally:
            runtime = time.monotonic() - start_time
            with Lock:
                Cumulative[fn.__name__].process(runtime)

    return profile_wrapper


# cumulative_data and backend_instance references are used
# only to retain the variables in scope until this method
# executes atexit
def dump_profiling_data(cumulative_data, backend_instance):
    if backend_instance is None:
        return

    output = {"measurements": []}
    for name, measurement in cumulative_data.items():
        output["measurements"].append(
            {
                "name": name,
                "duration": measurement._duration,
                "max": measurement._max,
                "min": measurement._min,
                "count": measurement._count,
            }
        )
    backend.emit_info_event("profiling_dump", {"data": output})


# Expensive, use only if necessary
def check_args(wrapped, args, kwargs, checkers):
    # target signature
    sig = inspect.signature(wrapped)
    try:
        # fails for wrong argument names or counts
        bound_args = sig.bind(*args, **kwargs)
        # add defaults for validation
        bound_args.apply_defaults()
    except TypeError:
        # binding failed
        raise
    # run custom checkers
    for checker in checkers:
        checker(bound_args.arguments)


def wrap_function_wrapper(target, name, wrapper_fn):
    """Call wrapt.wrap_function_wrapper, logging and swallowing any failure.

    Returns the wrapped object on success, or None if wrapping failed (e.g.
    the target module or attribute no longer exists in this package version).
    """
    try:
        return wrapt.wrap_function_wrapper(target, name, wrapper_fn)
    except Exception as e:
        backend.debug(f"Could not wrap {name}: {e}")
        return None


def wrapt_pre_hook(hook=None, enable="", modify_args=False):
    def decorator(h):
        return PrePostWrapper(pre_func=h, enable=enable, modify_args=modify_args)

    return decorator


def wrapt_post_hook(hook=None, enable="", modify_ret=False):
    def decorator(h):
        return PrePostWrapper(post_func=h, enable=enable, modify_ret=modify_ret)

    return decorator


# Needed when we need both pre- and post- hooks to a method wrapped using wrapt
class PrePostWrapper:
    __slots__ = ("_post", "_pre", "_modify_args", "_modify_ret", "_enable")

    def __init__(self, pre_func=None, post_func=None, enable="", modify_args=False, modify_ret=False):
        self._pre = measure_time(pre_func)
        self._post = measure_time(post_func)
        self._enable = enable
        self._modify_args = modify_args
        self._modify_ret = modify_ret

    def __call__(self, wrapped, instance, args, kwargs):
        backend.acousticBackend.poll()
        if not cfg.sensor_config.enabled(self._enable):
            return wrapped(*args, **kwargs)

        # pre-hook
        if self._pre:
            try:
                if self._modify_args:
                    args, kwargs = self._pre(wrapped, instance, args, kwargs)
                else:
                    self._pre(wrapped, instance, args, kwargs)
            except backend.Remediation:
                # block
                raise
            except Exception as e:
                backend.exception(e)

        # wrapped method
        wrapped = measure_time(wrapped)
        result = wrapped(*args, **kwargs)

        # post-hook
        if self._post:
            try:
                if self._modify_ret:
                    result = self._post(wrapped, instance, args, kwargs, result)
                else:
                    self._post(wrapped, instance, args, kwargs, result)

            except backend.Remediation:
                # block
                raise
            except Exception as e:
                backend.exception(e)

        return result


# Async version of PrePost wrapper
# Useful when hooks are installed on async functions and async generators
class AsyncPrePostWrapper:
    __slots__ = ("_post", "_pre", "_modify_args", "_modify_ret", "_enable", "_async_gen")

    def __init__(self, pre_func=None, post_func=None, enable="", modify_args=False, modify_ret=False, async_gen=False):
        self._pre = measure_time(pre_func)
        self._post = measure_time(post_func)
        self._enable = enable
        self._modify_args = modify_args
        self._modify_ret = modify_ret
        self._async_gen = async_gen

    def __call__(self, wrapped, instance, args, kwargs):
        if self._async_gen:
            # functions returning async generators
            async def generator_wrapper():
                backend.acousticBackend.poll()
                if not cfg.sensor_config.enabled(self._enable):
                    async for item in wrapped(*args, **kwargs):
                        yield item

                new_args, new_kwargs = args, kwargs
                if self._pre:
                    try:
                        if self._modify_args:
                            new_args, new_kwargs = await self._pre(wrapped, instance, args, kwargs)
                        else:
                            await self._pre(wrapped, instance, args, kwargs)
                    except backend.Remediation:
                        raise
                    except Exception as e:
                        backend.exception(e)

                results = measure_time(wrapped)(*new_args, **new_kwargs)

                if self._post:
                    try:
                        # expect modify_ret = True
                        async for item in results:
                            yield await self._post(wrapped, instance, new_args, new_kwargs, item)
                    except backend.Remediation:
                        raise
                    except Exception as e:
                        backend.exception(e)
                    finally:
                        if hasattr(results, "aclose"):
                            await results.aclose()
                else:
                    try:
                        # yield in all cases
                        async for item in results:
                            yield item
                    finally:
                        if hasattr(results, "aclose"):
                            await results.aclose()

            return generator_wrapper()

        else:
            # regular async functions
            async def async_wrapper():
                backend.acousticBackend.poll()
                if not cfg.sensor_config.enabled(self._enable):
                    return await wrapped(*args, **kwargs)

                # pre-hook
                new_args, new_kwargs = args, kwargs
                if self._pre:
                    try:
                        if self._modify_args:
                            new_args, new_kwargs = await self._pre(wrapped, instance, args, kwargs)
                        else:
                            await self._pre(wrapped, instance, args, kwargs)
                    except backend.Remediation:
                        raise
                    except Exception as e:
                        backend.exception(e)

                result = await measure_time(wrapped)(*new_args, **new_kwargs)

                # post-hook
                if self._post:
                    try:
                        if self._modify_ret:
                            result = await self._post(wrapped, instance, new_args, new_kwargs, result)
                        else:
                            await self._post(wrapped, instance, new_args, new_kwargs, result)
                    except backend.Remediation:
                        raise
                    except Exception as e:
                        backend.exception(e)

                return result

            return async_wrapper()
