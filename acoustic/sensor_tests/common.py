# Copyright (C) 2026 BlueRock Security, Inc.
# All rights reserved.


class TestCase:
    def __init__(
        self,
        name,
        *,
        module=None,
        policy="default/python.json",
        extra_flags=(),
        extra_deps=(),
        non_zero_exit=False,
        tolerate_internal_exceptions=False,
        event_parser=None,
    ):
        self.name = name
        self.module = module or name
        self.policy = policy
        self.extra_flags = extra_flags
        self.extra_deps = extra_deps
        self.non_zero_exit = non_zero_exit
        self.tolerate_internal_exceptions = tolerate_internal_exceptions
        self.event_parser = event_parser


def check_for_event(events, name, attributes={}):
    for data in events:
        if data["meta"]["name"] == name:
            found = True  # Assume we found the event, will change found if attrs don't match

            for k, v in attributes.items():
                if k not in data or data[k] != v:
                    found = False  # Attrs didn't match

            if found:
                print(f"event found: {data}")
                return True
            # Otherwise, let's continue to scan for the next events

    print(f"no {name} event with attributes {attributes}")
    return False
