# Copyright (C) 2025 BlueRock Security, Inc.
# All rights reserved.
import importlib.util
import wrapt
from enum import IntEnum
import uuid

from . import backend
from . import cfg
from . import wrapper
from .wrapper import AsyncPrePostWrapper

from pydantic import BaseModel


# NOTE: The source field in events is used to notify if a client or server is a source of an rpc message
# The hooks on server side should set source to client for messages that are received by the server.
class McpSource(IntEnum):
    SERVER = 0
    CLIENT = 1


# NOTE: The source field in events is used to notify if a client or server is a source of an rpc message
# The hooks on server side should set source to client for messages that are received by the server.


class EmptyResponse(BaseModel):
    tools: list = []
    prompts: list = []
    resources: list = []
    description: str = ""
    messages: list = []
    content: list = []
    structured_content: dict = {}
    is_Error: bool = False
    nextCursor: str = None  # for PaginatedResult


def get_arg(args, kwargs, position, name, default=None):
    if name in kwargs:
        return kwargs.get(name)
    elif len(args) > position:
        return args[position]
    else:
        return default


@wrapper.wrapt_pre_hook(enable="mcp")
def wrap_mcp_server_session_received_request(fn, instance, args, kwargs):
    responder = get_arg(args, kwargs, 0, "responder")
    if not responder:
        return
    request = responder.request
    request_id = request.root.id
    json_request = request.model_dump(by_alias=True, mode="json", exclude_none=True)

    # if received, store client entity_id ID in the instance
    if request and request.root.params and request.root.params.meta:
        if hasattr(request.root.params.meta, "entity_id"):
            instance.client_id = request.root.params.meta.entity_id
        if hasattr(request.root.params.meta, "session_id"):
            # BR client, overwrite current session ID with the one received
            instance.session_id = request.root.params.meta.session_id

    # Emit the server session_id after sync with client
    if not hasattr(instance, "_session_id_emitted"):
        instance._session_id_emitted = True
        backend.emit_info_event(
            "mcp_session_created",
            {
                "session_id": getattr(instance, "session_id", "null"),
                "source": McpSource.SERVER,
            },
        )

    backend.emit_event(
        "mcp_event",
        {
            "event": "server_received_request",
            "id": request_id,
            "message": json_request,
            "client_id": getattr(instance, "client_id", "null"),
            "session_id": getattr(instance, "session_id", "null"),
            "source": McpSource.CLIENT,
            "server_name": instance._init_options.server_name,
        },
    )


@wrapper.wrapt_pre_hook(enable="mcp")
def wrap_mcp_server_session_received_notification(fn, instance, args, kwargs):
    notification = get_arg(args, kwargs, 0, "notification")
    if not notification:
        return

    backend.emit_event(
        "mcp_event",
        {
            "event": "server_received_notification",
            "id": 0,
            "message": notification.model_dump(by_alias=True, mode="json", exclude_none=True),
            "client_id": getattr(instance, "client_id", "null"),
            "session_id": getattr(instance, "session_id", "null"),
            "source": McpSource.CLIENT,
            "server_name": instance._init_options.server_name,
        },
    )


@wrapper.wrapt_pre_hook(enable="mcp", modify_args=True)
def wrap_mcp_server_session_send_response(fn, instance, args, kwargs):
    request_id = get_arg(args, kwargs, 0, "request_id")
    response = get_arg(args, kwargs, 1, "response")
    if not response or not request_id:
        return args, kwargs

    RootModel = type(response)
    ResultModel = type(response.root)
    json_result = response.model_dump(by_alias=True, mode="json", exclude_none=True)
    try:
        backend.emit_event(
            "mcp_event",
            {
                "event": "server_send_response",
                "id": request_id,
                "message": {"result": json_result},
                "client_id": getattr(instance, "client_id", "null"),
                "session_id": getattr(instance, "session_id", "null"),
                "source": McpSource.SERVER,
                "server_name": instance._init_options.server_name,
            },
        )
    except backend.ModifyRemediation as e:
        result = ResultModel.model_validate(e.modification["result"], by_alias=True)
        kwargs["response"] = RootModel(result)
    except backend.Remediation:
        if cfg.sensor_config.mcp.remediation_exception:
            raise
        new_response = EmptyResponse()
        kwargs["response"] = new_response

    return args, kwargs


@wrapper.wrapt_pre_hook(enable="mcp")
def wrap_mcp_server_send_notification(fn, instance, args, kwargs):
    notification = get_arg(args, kwargs, 0, "notification")
    if not notification:
        return
    request_id = get_arg(args, kwargs, 1, "related_request_id", 0)
    json_result = notification.model_dump(by_alias=True, mode="json", exclude_none=True)  # This line was already here

    backend.emit_event(
        "mcp_event",
        {
            "event": "server_send_notification",
            "id": request_id,
            "message": json_result,
            "client_id": getattr(instance, "client_id", "null"),
            "session_id": getattr(instance, "session_id", "null"),
            "source": McpSource.SERVER,
            "server_name": instance._init_options.server_name,
        },
    )


@wrapper.wrapt_pre_hook(enable="mcp")
def wrap_mcp_client_send_notification(fn, instance, args, kwargs):
    notification = get_arg(args, kwargs, 0, "notification")
    if not notification:
        return
    request_id = get_arg(args, kwargs, 1, "related_request_id", 0)
    json_result = notification.model_dump(by_alias=True, mode="json", exclude_none=True)

    backend.emit_event(
        "mcp_event",
        {
            "event": "client_send_notification",
            "id": request_id,
            "message": json_result,
            "source": McpSource.CLIENT,
            "server_name": getattr(instance, "br_server_name", "null"),
            "session_id": getattr(instance, "session_id", "null"),
        },
    )


# cleanup the session ID, also notify backend
async def wrap_mcp_server_session_aexit_pre(fn, instance, args, kwargs):
    backend.emit_info_event(
        "mcp_session_terminated",
        {
            "client_id": getattr(instance, "client_id", "null"),
            "session_id": getattr(instance, "session_id", "null"),
            "source": McpSource.SERVER,
        },
    )


wrap_mcp_server_session_aexit = AsyncPrePostWrapper(pre_func=wrap_mcp_server_session_aexit_pre, enable="mcp")


# base session init - create session_id
@wrapper.wrapt_pre_hook(enable="mcp")
def wrap_mcp_shared_session_init(fn, instance, args, kwargs):
    # assign a session_id
    if not hasattr(instance, "session_id"):
        instance.session_id = str(uuid.uuid4())

    # safe to import if the wrapper has been applied
    from mcp.client.session import ClientSession

    # emit the session ID for clients on creation
    # for servers, wait till the client connection allow shared session IDs
    if isinstance(instance, ClientSession):
        backend.emit_info_event(
            "mcp_session_created",
            {
                "session_id": getattr(instance, "session_id", "null"),
                "source": McpSource.CLIENT,
            },
        )


async def wrap_mcp_client_session_exit_pre(fn, instance, args, kwargs):

    backend.emit_info_event(
        "mcp_session_terminated",
        {
            "session_id": getattr(instance, "session_id", "null"),
            "source": McpSource.CLIENT,
        },
    )


wrap_mcp_client_session_exit = AsyncPrePostWrapper(pre_func=wrap_mcp_client_session_exit_pre, enable="mcp")


@wrapper.wrapt_post_hook(enable="mcp")
def wrap_mcp_server_init(fn, instance, args, kwargs, ret):
    backend.emit_event(
        "mcp_server_init",
        {
            "server": {
                "name": instance.name,
                "title": get_arg(args, kwargs, 1, "title"),
                "description": get_arg(args, kwargs, 2, "description"),
                "version": instance.version,
                "instructions": instance.instructions,
            },
        },
    )


@wrapper.wrapt_post_hook(enable="mcp")
def wrap_mcp_add_tool(fn, instance, args, kwargs, tool):
    backend.emit_event(
        "mcp_server_add",
        {
            "element": {
                "type": "tool",
                "name": tool.name,
                "title": tool.title,
                "description": tool.description,
                "parameters": tool.parameters,
            },
        },
    )


@wrapper.wrapt_pre_hook(enable="mcp")
def wrap_mcp_add_resource(fn, instance, args, kwargs):
    resource = get_arg(args, kwargs, 0, "resource")
    if not resource:
        return
    backend.emit_event(
        "mcp_server_add",
        {
            "element": {
                "type": "resource",
                "name": resource.name,
                "title": resource.title,
                "description": resource.description,
                "uri": str(resource.uri),
            },
        },
    )


@wrapper.wrapt_pre_hook(enable="mcp")
def wrap_mcp_add_prompt(fn, instance, args, kwargs):
    prompt = get_arg(args, kwargs, 0, "prompt")
    if not prompt:
        return
    backend.emit_event(
        "mcp_server_add",
        {
            "element": {
                "type": "prompt",
                "name": prompt.name,
                "description": prompt.description,
                "arguments":
                # iterate prompt arguments and add them to a list
                [
                    {"name": argument.name, "description": argument.description, "required": argument.required}
                    for argument in prompt.arguments
                ],
            },
        },
    )


@wrapper.wrapt_pre_hook(enable="mcp")
def wrap_mcp_client_streamable_http_client(fn, instance, args, kwargs):
    # New SDK: streamable_http_client(url, *, http_client=None, ...)
    # auth is configured on the httpx.AsyncClient object, not passed directly
    url = get_arg(args, kwargs, 0, "url")
    if not url:
        return
    http_client = kwargs.get("http_client")
    auth = getattr(http_client, "auth", None) if http_client is not None else None
    backend.emit_event(
        "mcp_client_connect",
        {"server": {"type": "http", "url": url, "auth": auth is not None}},
    )


@wrapper.wrapt_pre_hook(enable="mcp")
def wrap_mcp_client_streamablehttp_client(fn, instance, args, kwargs):
    # Old SDK (<=1.23): streamablehttp_client(url, headers, timeout, sse_read_timeout,
    #                                          terminate_on_close, httpx_client_factory, auth)
    url = get_arg(args, kwargs, 0, "url")
    if not url:
        return
    auth = get_arg(args, kwargs, 6, "auth")
    backend.emit_event(
        "mcp_client_connect",
        {"server": {"type": "http", "url": url, "auth": auth is not None}},
    )


@wrapper.wrapt_pre_hook(enable="mcp")
def wrap_mcp_client_sse_client(fn, instance, args, kwargs):
    url = get_arg(args, kwargs, 0, "url")
    if not url:
        return
    auth = get_arg(args, kwargs, 5, "auth")
    backend.emit_event(
        "mcp_client_connect",
        {"server": {"type": "sse", "url": url, "auth": auth is not None}},
    )


@wrapper.wrapt_pre_hook(enable="mcp")
def wrap_mcp_client_websocket_client(fn, instance, args, kwargs):
    url = get_arg(args, kwargs, 0, "url")
    if not url:
        return
    backend.emit_event("mcp_client_connect", {"server": {"type": "websocket", "url": url}})


@wrapper.wrapt_pre_hook(enable="mcp")
def wrap_mcp_client_stdio_client(fn, instance, args, kwargs):
    stdio_server = get_arg(args, kwargs, 0, "server")
    if not stdio_server:
        return
    backend.emit_event(
        "mcp_client_connect",
        {
            "server": {
                "type": "stdio",
                "command": stdio_server.command,
                "args": stdio_server.args,
            },
        },
    )


# FastMCP hooks
@wrapper.wrapt_pre_hook(enable="mcp")
def wrap_fastmcp_add_tool(fn, instance, args, kwargs):
    tool = get_arg(args, kwargs, 0, "tool")
    if not tool:
        return
    backend.emit_event(
        "mcp_server_add",
        {
            "element": {
                "type": "tool",
                "name": tool.name,
                "title": tool.title,
                "description": tool.description,
                "parameters": tool.parameters,
            },
        },
    )


# Hooks on a Client side of a Session: send_request and received_response which is a return value of this call


async def wrap_mcp_session_send_request_pre(fn, instance, args, kwargs):
    request = get_arg(args, kwargs, 0, "request")
    if not request:
        return args, kwargs

    # import mcp types here to avoid global dependecy on mcp
    from mcp import types

    # makes use of _meta field (https://modelcontextprotocol.io/specification/2025-06-18/basic/index#meta)
    # Todo: Inject params? Some requests like Ping don't have params/meta.
    # They are probably not very interesting for traceability right now
    if hasattr(request.root, "params") and request.root.params is not None:
        if request.root.params.meta is None:
            request.root.params.meta = types.RequestParams.Meta()
        # Pydantic will handle the aliasing to `_meta`.
        request.root.params.meta.entity_id = backend.component_id
        request.root.params.meta.session_id = getattr(instance, "session_id", "null")

    # current request ID
    request_id = instance._request_id
    try:
        backend.emit_event(
            "mcp_event",
            {
                "event": "client_send_request",
                "id": request_id,
                "message": request.model_dump(by_alias=True, mode="json", exclude_none=True),
                "session_id": getattr(instance, "session_id", "null"),
                "source": McpSource.CLIENT,
                "server_name": getattr(instance, "br_server_name", "null"),
            },
        )
    except backend.Remediation:
        if cfg.sensor_config.mcp.remediation_exception:
            raise
        new_request = types.ErrorData(code=types.INVALID_PARAMS, message="Remediation hook is executed", data=None)
        kwargs["request"] = new_request

    # for future filtering and mutating of the request
    return args, kwargs


async def wrap_mcp_session_send_request_post(fn, instance, args, kwargs, response):
    request_id = instance._request_id

    if hasattr(response, "root"):
        RootModel = type(response)
        ResultModel = type(response.root)
    else:
        RootModel = type(response)
        ResultModel = RootModel

    # serverInfo is only available on the response to an `initialize` request.
    # store it in the session instance for tagging later requests
    if hasattr(response, "serverInfo") and response.serverInfo:
        instance.br_server_name = response.serverInfo.name

    try:
        backend.emit_event(
            "mcp_event",
            {
                "event": "client_received_response",
                "id": request_id,
                "message": {"result": response.model_dump(by_alias=True, mode="json", exclude_none=True)},
                "session_id": getattr(instance, "session_id", "null"),
                "source": McpSource.SERVER,
                "server_name": getattr(instance, "br_server_name", "null"),
            },
        )
    except backend.ModifyRemediation as e:
        result = ResultModel.model_validate(e.modification["result"], by_alias=True)
        if hasattr(response, "root"):
            response = RootModel(result)
        else:
            response = result
    except backend.Remediation:
        if cfg.sensor_config.mcp.remediation_exception:
            raise
        response = EmptyResponse()

    return response


wrap_mcp_session_send_request = AsyncPrePostWrapper(
    wrap_mcp_session_send_request_pre, wrap_mcp_session_send_request_post, "mcp", modify_args=True, modify_ret=True
)


@wrapper.wrapt_pre_hook(enable="mcp")
def wrap_mcp_client_session_received_request(fn, instance, args, kwargs):
    responder = get_arg(args, kwargs, 0, "responder")
    if not responder:
        return
    request = responder.request
    request_id = request.root.id
    json_request = request.model_dump(by_alias=True, mode="json", exclude_none=True)
    backend.emit_event(
        "mcp_event",
        {
            "event": "client_received_request",
            "id": request_id,
            "message": json_request,
            "session_id": getattr(instance, "session_id", "null"),
            "source": McpSource.SERVER,
            "server_name": getattr(instance, "br_server_name", "null"),
        },
    )


@wrapper.wrapt_pre_hook(enable="mcp")
def wrap_mcp_client_session_received_notification(fn, instance, args, kwargs):
    notification = get_arg(args, kwargs, 0, "notification")
    if not notification:
        return

    backend.emit_event(
        "mcp_event",
        {
            "event": "client_received_notification",
            "id": 0,
            "message": notification.model_dump(by_alias=True, mode="json", exclude_none=True),
            "session_id": getattr(instance, "session_id", "null"),
            "source": McpSource.SERVER,
            "server_name": getattr(instance, "br_server_name", "null"),
        },
    )


@wrapper.wrapt_pre_hook(enable="mcp")
def wrap_mcp_client_session_send_response(fn, instance, args, kwargs):
    request_id = get_arg(args, kwargs, 0, "request_id")
    response = get_arg(args, kwargs, 1, "response")
    if not response or not request_id:
        return
    json_result = response.model_dump(by_alias=True, mode="json", exclude_none=True)

    backend.emit_event(
        "mcp_event",
        {
            "event": "client_send_response",
            "id": request_id,
            "message": {"result": json_result},
            "session_id": getattr(instance, "session_id", "null"),
            "source": McpSource.CLIENT,
            "server_name": getattr(instance, "br_server_name", "null"),
        },
    )


@wrapt.when_imported("mcp")
def apply_mcp_hooks(mcp):
    wrapper.wrap_function_wrapper(
        "mcp.server.session", "ServerSession._received_request", wrap_mcp_server_session_received_request
    )
    wrapper.wrap_function_wrapper(
        "mcp.server.session", "ServerSession._received_notification", wrap_mcp_server_session_received_notification
    )
    wrapper.wrap_function_wrapper(
        "mcp.server.session", "ServerSession._send_response", wrap_mcp_server_session_send_response
    )
    wrapper.wrap_function_wrapper("mcp.server.session", "ServerSession.__aexit__", wrap_mcp_server_session_aexit)
    wrapper.wrap_function_wrapper(
        "mcp.server.session", "ServerSession.send_notification", wrap_mcp_server_send_notification
    )
    wrapper.wrap_function_wrapper(
        "mcp.client.session", "ClientSession.send_notification", wrap_mcp_client_send_notification
    )
    # mcp.server.fastmcp was renamed to mcp.server.mcpserver in newer versions
    if importlib.util.find_spec("mcp.server.mcpserver"):
        _server_pkg = "mcp.server.mcpserver"
    else:
        _server_pkg = "mcp.server.fastmcp"
    wrapper.wrap_function_wrapper(f"{_server_pkg}.server", "MCPServer.__init__", wrap_mcp_server_init)
    wrapper.wrap_function_wrapper(f"{_server_pkg}.tools", "ToolManager.add_tool", wrap_mcp_add_tool)
    wrapper.wrap_function_wrapper(f"{_server_pkg}.resources", "ResourceManager.add_resource", wrap_mcp_add_resource)
    wrapper.wrap_function_wrapper(f"{_server_pkg}.prompts", "PromptManager.add_prompt", wrap_mcp_add_prompt)
    wrapper.wrap_function_wrapper("mcp.shared.session", "BaseSession.send_request", wrap_mcp_session_send_request)
    # Explicitly wrap ClientSession and ServerSession to ensure hooks apply
    # even if inheritance wrapping is flaky
    wrapper.wrap_function_wrapper("mcp.client.session", "ClientSession.send_request", wrap_mcp_session_send_request)
    wrapper.wrap_function_wrapper("mcp.server.session", "ServerSession.send_request", wrap_mcp_session_send_request)
    wrapper.wrap_function_wrapper("mcp.client.sse", "sse_client", wrap_mcp_client_sse_client)
    wrapper.wrap_function_wrapper("mcp.client.stdio", "stdio_client", wrap_mcp_client_stdio_client)
    wrapper.wrap_function_wrapper(
        "mcp.client.session", "ClientSession._received_request", wrap_mcp_client_session_received_request
    )
    wrapper.wrap_function_wrapper(
        "mcp.client.session", "ClientSession._received_notification", wrap_mcp_client_session_received_notification
    )
    wrapper.wrap_function_wrapper(
        "mcp.client.session", "ClientSession._send_response", wrap_mcp_client_session_send_response
    )
    wrapper.wrap_function_wrapper("mcp.shared.session", "BaseSession.__init__", wrap_mcp_shared_session_init)
    wrapper.wrap_function_wrapper("mcp.client.session", "ClientSession.__aexit__", wrap_mcp_client_session_exit)


@wrapt.when_imported("mcp.client.websocket")
def apply_mcp_websocket_hooks(websocket):
    wrapper.wrap_function_wrapper("mcp.client.websocket", "websocket_client", wrap_mcp_client_websocket_client)


@wrapt.when_imported("mcp.client.streamable_http")
def apply_mcp_http_hooks(http):
    if hasattr(http, "streamable_http_client"):
        # New SDK (>=1.26): streamable_http_client(url, *, http_client=None, ...)
        wrapper.wrap_function_wrapper(
            "mcp.client.streamable_http",
            "streamable_http_client",
            wrap_mcp_client_streamable_http_client,
        )
    else:
        # Old SDK (<=1.23): streamablehttp_client(url, ..., auth)
        wrapper.wrap_function_wrapper(
            "mcp.client.streamable_http",
            "streamablehttp_client",
            wrap_mcp_client_streamablehttp_client,
        )


@wrapper.wrapt_pre_hook(enable="mcp")
def wrap_fastmcp_local_provider_add_component(fn, instance, args, kwargs):
    """New-style fastmcp hook: dispatches mcp_server_add events from LocalProvider._add_component."""
    from fastmcp.prompts.prompt import Prompt
    from fastmcp.resources.resource import Resource
    from fastmcp.tools.tool import Tool

    component = get_arg(args, kwargs, 0, "component")
    if not component:
        return

    if isinstance(component, Tool):
        backend.emit_event(
            "mcp_server_add",
            {
                "element": {
                    "type": "tool",
                    "name": component.name,
                    "title": component.title,
                    "description": component.description,
                    "parameters": component.parameters,
                },
            },
        )
    elif isinstance(component, Resource):
        backend.emit_event(
            "mcp_server_add",
            {
                "element": {
                    "type": "resource",
                    "name": component.name,
                    "title": component.title,
                    "description": component.description,
                    "uri": str(component.uri),
                },
            },
        )
    elif isinstance(component, Prompt):
        backend.emit_event(
            "mcp_server_add",
            {
                "element": {
                    "type": "prompt",
                    "name": component.name,
                    "description": component.description,
                    "arguments": [
                        {"name": arg.name, "description": arg.description, "required": arg.required}
                        for arg in (component.arguments or [])
                    ],
                },
            },
        )


@wrapt.when_imported("fastmcp")
def apply_fastmcp_hooks(fastmcp):
    # Old-style fastmcp had separate ToolManager/ResourceManager/PromptManager classes.
    # New-style fastmcp uses LocalProvider._add_component as the central registration point.
    if importlib.util.find_spec("fastmcp.tools.tool_manager"):
        wrapper.wrap_function_wrapper("fastmcp.tools.tool_manager", "ToolManager.add_tool", wrap_fastmcp_add_tool)
        wrapper.wrap_function_wrapper(
            "fastmcp.resources.resource_manager", "ResourceManager.add_resource", wrap_mcp_add_resource
        )
        wrapper.wrap_function_wrapper("fastmcp.prompts.prompt_manager", "PromptManager.add_prompt", wrap_mcp_add_prompt)
    else:
        try:
            has_local_provider = (
                importlib.util.find_spec("fastmcp.server.providers.local_provider.local_provider") is not None
            )
        except (ModuleNotFoundError, ValueError):
            has_local_provider = False
        if has_local_provider:
            wrapper.wrap_function_wrapper(
                "fastmcp.server.providers.local_provider.local_provider",
                "LocalProvider._add_component",
                wrap_fastmcp_local_provider_add_component,
            )
