"""WorkflowNodeTool — wraps a Dify workflow node as an agent tool.

This allows the Agent node to call other workflow nodes (Knowledge Retrieval,
HTTP Request, etc.) as tools during LLM function-calling. The tool wraps the
target node's core logic and exposes it via the standard Tool interface.

Phase 1 supports:
- knowledge-retrieval: wraps DatasetRetrieval.knowledge_retrieval() with a
  single ``query`` parameter exposed to the LLM.

The handler functions live in ``handlers.py`` and are dispatched on
``self._node_type``. New node types can be added by extending the dispatch
in ``_invoke()``.
"""

from __future__ import annotations

from collections.abc import Generator
from typing import Any

from core.tools.__base.tool import Tool
from core.tools.__base.tool_runtime import ToolRuntime
from core.tools.entities.common_entities import I18nObject
from core.tools.entities.tool_entities import (
    ToolDescription,
    ToolEntity,
    ToolIdentity,
    ToolInvokeMessage,
    ToolParameter,
    ToolProviderType,
)
from core.tools.workflow_node_tool.template_utils import extract_http_template_parameter_names


class WorkflowNodeTool(Tool):
    """A tool that wraps a workflow node for use by the agent.

    Instances are created via :meth:`from_node_config` which builds the
    ``ToolEntity`` (identity, description, parameters) from the target node's
    configuration in the workflow graph.
    """

    def __init__(
        self,
        entity: ToolEntity,
        runtime: ToolRuntime,
        *,
        node_id: str,
        node_type: str,
        node_config: dict[str, Any],
        tenant_id: str,
        user_id: str,
        app_id: str,
    ) -> None:
        super().__init__(entity, runtime)
        self._node_id = node_id
        self._node_type = node_type
        self._node_config = node_config
        self._tenant_id = tenant_id
        self._user_id = user_id
        self._app_id = app_id

    @property
    def node_id(self) -> str:
        return self._node_id

    @property
    def node_type(self) -> str:
        return self._node_type

    @property
    def node_config(self) -> dict[str, Any]:
        return self._node_config

    @property
    def tenant_id(self) -> str:
        return self._tenant_id

    @property
    def user_id(self) -> str:
        return self._user_id

    @property
    def app_id(self) -> str:
        return self._app_id

    def fork_tool_runtime(self, runtime: ToolRuntime) -> WorkflowNodeTool:
        return WorkflowNodeTool(
            entity=self.entity.model_copy(),
            runtime=runtime,
            node_id=self._node_id,
            node_type=self._node_type,
            node_config=self._node_config,
            tenant_id=self._tenant_id,
            user_id=self._user_id,
            app_id=self._app_id,
        )

    def tool_provider_type(self) -> ToolProviderType:
        return ToolProviderType.WORKFLOW_NODE

    def get_runtime_parameters(
        self,
        conversation_id: str | None = None,
        app_id: str | None = None,
        message_id: str | None = None,
    ) -> list[ToolParameter]:
        return self.entity.parameters

    def _invoke(
        self,
        user_id: str,
        tool_parameters: dict[str, Any],
        conversation_id: str | None = None,
        app_id: str | None = None,
        message_id: str | None = None,
    ) -> Generator[ToolInvokeMessage, None, None]:
        if self._node_type == "knowledge-retrieval":
            from .handlers.knowledge_retrieval_handler import invoke_knowledge_retrieval

            yield from invoke_knowledge_retrieval(
                tool=self,
                tool_parameters=tool_parameters,
            )
        elif self._node_type == "http-request":
            from .handlers.http_request_handler import invoke_http_request

            yield from invoke_http_request(
                tool=self,
                tool_parameters=tool_parameters,
            )
        else:
            yield self.create_text_message(
                text=f"Unsupported node type for agent tool: {self._node_type}"
            )

    @classmethod
    def from_node_config(
        cls,
        *,
        node_id: str,
        node_type: str,
        node_config: dict[str, Any],
        node_title: str,
        custom_description: str,
        tenant_id: str,
        user_id: str,
        app_id: str,
    ) -> WorkflowNodeTool:
        """Build a WorkflowNodeTool instance from a workflow node config.

        :param node_id: ID of the target node in the workflow graph.
        :param node_type: e.g. ``"knowledge-retrieval"`` or ``"http-request"``.
        :param node_config: The target node's ``data`` dict from the workflow graph.
        :param node_title: Human-readable label for the node (used as tool label).
        :param custom_description: User-provided LLM description appended to the
            auto-generated default description.
        :param tenant_id: Workspace tenant id.
        :param user_id: Invoking user id.
        :param app_id: Owning app id.
        """
        parameters = _build_parameters_for_node_type(node_type, node_config)
        description = _build_description(node_type, custom_description)
        tool_name = _normalize_tool_name(node_id, node_title)

        entity = ToolEntity(
            identity=ToolIdentity(
                provider="workflow_node",
                author="dify",
                name=tool_name,
                label=I18nObject(en_US=node_title, zh_Hans=node_title),
            ),
            parameters=parameters,
            description=ToolDescription(
                human=I18nObject(en_US=description, zh_Hans=description),
                llm=description,
            ),
        )

        return cls(
            entity=entity,
            runtime=ToolRuntime(tenant_id=tenant_id),
            node_id=node_id,
            node_type=node_type,
            node_config=node_config,
            tenant_id=tenant_id,
            user_id=user_id,
            app_id=app_id,
        )


def _build_parameters_for_node_type(node_type: str, node_config: dict[str, Any]) -> list[ToolParameter]:
    """Auto-generate tool parameters per supported node type."""
    if node_type == "knowledge-retrieval":
        return [
            ToolParameter(
                name="query",
                label=I18nObject(en_US="Query", zh_Hans="查询"),
                human_description=I18nObject(
                    en_US="The search query to retrieve relevant knowledge.",
                    zh_Hans="用于检索相关知识的查询语句。",
                ),
                type=ToolParameter.ToolParameterType.STRING,
                form=ToolParameter.ToolParameterForm.LLM,
                llm_description="The search query to retrieve relevant knowledge from the knowledge base.",
                required=True,
                default="",
                placeholder=I18nObject(en_US="Enter a search query", zh_Hans="输入查询内容"),
            ),
        ]
    if node_type == "http-request":
        parameter_names = extract_http_template_parameter_names(node_config)
        return [
            ToolParameter(
                name=parameter_name,
                label=I18nObject(en_US=parameter_name, zh_Hans=parameter_name),
                human_description=I18nObject(
                    en_US=f"Value for template variable '{parameter_name}' in the HTTP Request node.",
                    zh_Hans=f"HTTP 请求节点中模板变量 '{parameter_name}' 的值。",
                ),
                type=ToolParameter.ToolParameterType.STRING,
                form=ToolParameter.ToolParameterForm.LLM,
                llm_description=f"Value for the '{parameter_name}' template variable used by the HTTP request node.",
                required=True,
                default="",
                placeholder=I18nObject(en_US=f"Enter {parameter_name}", zh_Hans=f"输入 {parameter_name}"),
            )
            for parameter_name in parameter_names
        ]
    return []


def _build_description(node_type: str, custom_description: str) -> str:
    """Combine an auto-generated default description with the user's custom one."""
    defaults = {
        "knowledge-retrieval": "Search the knowledge base for relevant information.",
        "http-request": "Make an HTTP request to a configured endpoint.",
    }
    base = defaults.get(node_type, f"Invoke the {node_type} workflow node.")
    if custom_description.strip():
        return f"{base} {custom_description.strip()}"
    return base


def _normalize_tool_name(node_id: str, node_title: str) -> str:
    """Build a stable tool name. Tool names are exposed to the LLM, so
    prefer human-readable while keeping uniqueness via the node id suffix."""
    safe_title = "".join(c if c.isalnum() or c in ("_", "-") else "_" for c in node_title.strip())
    if not safe_title:
        safe_title = "node_tool"
    return f"{safe_title}_{node_id[:8]}"
