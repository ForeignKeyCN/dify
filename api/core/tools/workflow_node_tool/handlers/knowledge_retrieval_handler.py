"""Knowledge Retrieval handler for WorkflowNodeTool.

Wraps the same retrieval logic used by the KnowledgeRetrievalNode but bypasses
the graph runtime — the agent already has tenant/user/app context, and the
``query`` is provided directly by the LLM via tool parameters.
"""

from __future__ import annotations

from collections.abc import Generator
from typing import TYPE_CHECKING, Any

from core.app.app_config.entities import DatasetRetrieveConfigEntity
from core.rag.retrieval.dataset_retrieval import DatasetRetrieval
from core.tools.entities.tool_entities import ToolInvokeMessage
from core.workflow.nodes.knowledge_retrieval.retrieval import KnowledgeRetrievalRequest, Source

if TYPE_CHECKING:
    from ..tool import WorkflowNodeTool


def invoke_knowledge_retrieval(
    *,
    tool: WorkflowNodeTool,
    tool_parameters: dict[str, Any],
) -> Generator[ToolInvokeMessage, None, None]:
    query = tool_parameters.get("query", "").strip() if tool_parameters.get("query") else ""
    if not query:
        yield tool.create_text_message(text="No query provided.")
        return

    node_config = tool.node_config
    dataset_ids: list[str] = node_config.get("dataset_ids") or []
    if not dataset_ids:
        yield tool.create_text_message(text="No knowledge bases configured on this node.")
        return

    retrieval_mode = str(node_config.get("retrieval_mode") or "multiple")
    rag = DatasetRetrieval()
    sources: list[Source] = []

    if retrieval_mode == DatasetRetrieveConfigEntity.RetrieveStrategy.SINGLE:
        single_cfg = node_config.get("single_retrieval_config") or {}
        model = single_cfg.get("model") or {}
        sources = rag.knowledge_retrieval(
            request=KnowledgeRetrievalRequest(
                tenant_id=tool.tenant_id,
                user_id=tool.user_id,
                app_id=tool.app_id,
                user_from="account",
                dataset_ids=dataset_ids,
                retrieval_mode=DatasetRetrieveConfigEntity.RetrieveStrategy.SINGLE.value,
                completion_params=model.get("completion_params"),
                model_provider=model.get("provider"),
                model_mode=model.get("mode"),
                model_name=model.get("name"),
                query=query,
            )
        )
    else:
        multi_cfg = node_config.get("multiple_retrieval_config") or {}
        sources = rag.knowledge_retrieval(
            request=KnowledgeRetrievalRequest(
                tenant_id=tool.tenant_id,
                user_id=tool.user_id,
                app_id=tool.app_id,
                user_from="account",
                dataset_ids=dataset_ids,
                retrieval_mode=DatasetRetrieveConfigEntity.RetrieveStrategy.MULTIPLE.value,
                query=query,
                top_k=int(multi_cfg.get("top_k") or 4),
                score_threshold=float(multi_cfg.get("score_threshold") or 0.0),
                reranking_mode=str(multi_cfg.get("reranking_mode") or "reranking_model"),
                reranking_enable=bool(multi_cfg.get("reranking_enable") or False),
            )
        )

    if not sources:
        yield tool.create_text_message(text="No relevant results found.")
        return

    # Emit a JSON message with the structured sources for downstream use,
    # plus a text message with the concatenated content for the LLM to read.
    yield tool.create_json_message(
        object={"sources": [source.model_dump(by_alias=True) for source in sources]},
    )
    text_chunks = [source.content for source in sources if source.content]
    yield tool.create_text_message(text="\n\n---\n\n".join(text_chunks))
