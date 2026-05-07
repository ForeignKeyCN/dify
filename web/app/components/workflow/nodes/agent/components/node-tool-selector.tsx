import type { FC } from 'react'
import type { NodeToolConfig } from '../types'
import { memo, useCallback, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import Checkbox from '@/app/components/base/checkbox'
import Textarea from '@/app/components/base/textarea'
import { BlockEnum } from '@/app/components/workflow/types'

const SUPPORTED_NODE_TYPES: string[] = [BlockEnum.KnowledgeRetrieval, BlockEnum.HttpRequest]

type AvailableNode = {
  id: string
  data: {
    type: string
    title?: string
    desc?: string
  }
}

type NodeToolSelectorProps = {
  nodeId: string
  value: NodeToolConfig[]
  onChange: (value: NodeToolConfig[]) => void
  availableNodes: AvailableNode[]
  readOnly?: boolean
}

const NodeToolSelector: FC<NodeToolSelectorProps> = ({
  nodeId,
  value,
  onChange,
  availableNodes,
  readOnly,
}) => {
  const { t } = useTranslation()

  const eligibleNodes = useMemo(() => {
    return availableNodes.filter(node =>
      node.id !== nodeId
      && SUPPORTED_NODE_TYPES.includes(node.data?.type),
    )
  }, [availableNodes, nodeId])

  const valueByNodeId = useMemo(() => {
    const map: Record<string, NodeToolConfig> = {}
    for (const item of value)
      map[item.node_id] = item

    return map
  }, [value])

  const handleToggle = useCallback((node: AvailableNode) => {
    const existing = valueByNodeId[node.id]
    if (existing) {
      // Toggle the enabled flag (keep description in case user re-enables)
      onChange(value.map(item =>
        item.node_id === node.id ? { ...item, enabled: !item.enabled } : item,
      ))
    }
    else {
      onChange([
        ...value,
        {
          node_id: node.id,
          node_type: node.data.type,
          enabled: true,
          description: '',
        },
      ])
    }
  }, [value, valueByNodeId, onChange])

  const handleDescriptionChange = useCallback((nodeId: string, description: string) => {
    onChange(value.map(item =>
      item.node_id === nodeId ? { ...item, description } : item,
    ))
  }, [value, onChange])

  if (eligibleNodes.length === 0) {
    return (
      <div className="rounded-lg border border-dashed border-divider-regular p-3 system-xs-regular text-text-tertiary">
        {t('nodes.agent.nodeTools.empty', { ns: 'workflow' })}
      </div>
    )
  }

  return (
    <div className="space-y-2">
      {eligibleNodes.map((node) => {
        const config = valueByNodeId[node.id]
        const isEnabled = !!config?.enabled
        return (
          <div
            key={node.id}
            className="rounded-lg border border-components-panel-border bg-components-panel-on-panel-item-bg p-2"
          >
            <div className="flex items-center gap-2">
              <Checkbox
                checked={isEnabled}
                disabled={readOnly}
                onCheck={() => !readOnly && handleToggle(node)}
              />
              <div className="grow truncate system-sm-medium text-text-secondary">
                {node.data.title || node.id}
              </div>
              <span className="shrink-0 system-2xs-medium-uppercase text-text-tertiary">
                {node.data.type}
              </span>
            </div>
            {isEnabled && (
              <div className="mt-2">
                <Textarea
                  size="small"
                  className="px-2"
                  value={config?.description || ''}
                  disabled={readOnly}
                  rows={2}
                  placeholder={t('nodes.agent.nodeTools.descriptionPlaceholder', { ns: 'workflow' })}
                  onChange={e => handleDescriptionChange(node.id, e.target.value)}
                />
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}

NodeToolSelector.displayName = 'NodeToolSelector'

export default memo(NodeToolSelector)
