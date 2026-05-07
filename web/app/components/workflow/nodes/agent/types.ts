import type { ToolVarInputs } from '../tool/types'
import type { PluginMeta } from '@/app/components/plugins/types'
import type { CommonNodeType, Memory } from '@/app/components/workflow/types'

export type NodeToolConfig = {
  node_id: string
  node_type: string
  enabled: boolean
  description: string
}

export type AgentNodeType = CommonNodeType & {
  agent_strategy_provider_name?: string
  agent_strategy_name?: string
  agent_strategy_label?: string
  agent_parameters?: ToolVarInputs
  meta?: PluginMeta
  output_schema: Record<string, unknown>
  plugin_unique_identifier?: string
  memory?: Memory
  version?: string
  tool_node_version?: string
  node_tools?: NodeToolConfig[]
}

export const AgentFeature = {
  HISTORY_MESSAGES: 'history-messages',
} as const
