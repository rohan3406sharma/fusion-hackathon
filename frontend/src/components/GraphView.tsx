import { forwardRef, useEffect, useImperativeHandle, useRef } from 'react'
import cytoscape, { type Core } from 'cytoscape'
import type { EntityImpact, GraphPayload } from '../api/types'
import { tieredLayout } from '../lib/layout'
import { STATUS_COLOR } from '../lib/colors'

export interface GraphHandle { fit: () => void; zoomIn: () => void; zoomOut: () => void; reset: () => void }
interface Props {
  graph: GraphPayload
  impacts: Map<string, EntityImpact>
  visible: Set<string>
  selectedId: string | null
  pathIds: string[]
  showFinancial: boolean
  layout: 'tiered' | 'force'
  onSelect: (id: string | null) => void
}
const SHAPE: Record<string, string> = {
  agricultural_producer: 'ellipse', agricultural_input: 'ellipse', utility: 'ellipse', processor: 'rectangle', manufacturer: 'rectangle',
  packaging_supplier: 'rectangle', cold_storage: 'diamond', transport_operator: 'diamond', port_hub: 'diamond',
  distribution_centre: 'hexagon', wholesaler: 'hexagon', retailer: 'hexagon', financial: 'tag',
}
export const SHAPE_LEGEND = [['ellipse', 'Farms, inputs, utilities'], ['rectangle', 'Processing, manufacturing, packaging'], ['diamond', 'Cold chain, transport, ports'], ['hexagon', 'Distribution & retail'], ['tag', 'Lenders / insurers']]

/** Supply-channel adjacency walk: returns hop distance for every node reachable up/downstream of `start`. */
export function walk(graph: GraphPayload, start: string, dir: 'up' | 'down') {
  const adj = new Map<string, { to: string; id: string }[]>()
  graph.edges.filter((e) => e.channel === 'supply').forEach((e) => {
    const [a, b] = dir === 'down' ? [e.source, e.target] : [e.target, e.source]
    adj.set(a, [...(adj.get(a) ?? []), { to: b, id: e.id }])
  })
  const nodes = new Map<string, number>([[start, 0]]); const edges = new Set<string>(); const q = [start]
  while (q.length) {
    const u = q.shift()!
    for (const { to, id } of adj.get(u) ?? []) { edges.add(id); if (!nodes.has(to)) { nodes.set(to, nodes.get(u)! + 1); q.push(to) } }
  }
  return { nodes, edges }
}

const GraphView = forwardRef<GraphHandle, Props>(function GraphView({ graph, impacts, visible, selectedId, pathIds, showFinancial, layout, onSelect }, ref) {
  const box = useRef<HTMLDivElement>(null)
  const cy = useRef<Core | null>(null)
  const onSelectRef = useRef(onSelect)
  onSelectRef.current = onSelect

  useImperativeHandle(ref, () => ({
    fit: () => cy.current?.fit(undefined, 30),
    zoomIn: () => cy.current && cy.current.zoom({ level: cy.current.zoom() * 1.25, renderedPosition: { x: cy.current.width() / 2, y: cy.current.height() / 2 } }),
    zoomOut: () => cy.current && cy.current.zoom({ level: cy.current.zoom() / 1.25, renderedPosition: { x: cy.current.width() / 2, y: cy.current.height() / 2 } }),
    reset: () => { cy.current?.elements().removeClass('faded up down sel pathn pathe'); onSelectRef.current(null); cy.current?.layout(layoutOpts()).run(); cy.current?.fit(undefined, 30) },
  }))

  const layoutOpts = () => (layout === 'tiered'
    ? { name: 'preset', positions: (n: cytoscape.NodeSingular) => { const p = pos[n.id()]; const portrait = (box.current?.clientHeight ?? 0) > (box.current?.clientWidth ?? 1) * 1.1; return portrait ? { x: p.y * 1.1, y: p.x * 0.9 } : p }, fit: true, padding: 30 } as cytoscape.LayoutOptions
    : { name: 'cose', animate: false, nodeRepulsion: () => 9000, idealEdgeLength: () => 70, fit: true, padding: 30, randomize: false } as cytoscape.LayoutOptions)
  const pos = useRef(tieredLayout(graph.nodes)).current

  // init once
  useEffect(() => {
    if (!box.current) return
    const instance = cytoscape({
      container: box.current, minZoom: 0.15, maxZoom: 3, wheelSensitivity: 0.25,
      elements: [
        ...graph.nodes.map((n) => ({ data: { id: n.id, label: n.name, etype: n.entity_type, synthetic: n.synthetic, size: 14 + Math.sqrt(n.value_added_musd) * 1.6, shape: SHAPE[n.entity_type] ?? 'ellipse', status: 'unaffected', dis: 0 } })),
        ...graph.edges.map((e) => ({ data: { id: e.id, source: e.source, target: e.target, dep: e.dependency, channel: e.channel }, classes: e.channel === 'financial' ? 'fin' : '' })),
      ],
      style: [
        { selector: 'node', style: { width: 'data(size)', height: 'data(size)', shape: 'data(shape)' as any, 'background-color': STATUS_COLOR.unaffected, 'border-width': 1.2, 'border-color': '#1A1A1A', label: 'data(label)', 'font-size': 8, 'font-family': 'Inter, sans-serif', color: '#1A1A1A', 'min-zoomed-font-size': 9, 'text-valign': 'bottom', 'text-margin-y': 3, 'text-wrap': 'ellipsis', 'text-max-width': '90px' } },
        { selector: 'node[?synthetic]', style: { 'border-style': 'dashed' } },
        { selector: 'node[status = "direct"]', style: { 'background-color': STATUS_COLOR.direct } },
        { selector: 'node[status = "propagated"]', style: { 'background-color': STATUS_COLOR.propagated, 'background-opacity': 'mapData(dis, 0, 1, 0.45, 1)' as any } },
        { selector: 'edge', style: { width: 'mapData(dep, 0, 1, 0.4, 2.4)' as any, 'line-color': '#B8AFA4', 'target-arrow-color': '#B8AFA4', 'target-arrow-shape': 'triangle', 'arrow-scale': 0.6, 'curve-style': 'bezier', opacity: 0.45 } },
        { selector: 'edge.fin', style: { 'line-style': 'dotted', 'line-color': '#6C6863', 'target-arrow-color': '#6C6863', opacity: 0.6 } },
        { selector: '.faded', style: { opacity: 0.08 } },
        { selector: 'edge.up', style: { 'line-color': '#1A1A1A', 'target-arrow-color': '#1A1A1A', opacity: 0.8 } },
        { selector: 'edge.down', style: { 'line-color': '#9A7B17', 'target-arrow-color': '#9A7B17', opacity: 0.9 } },
        { selector: 'node.up', style: { 'border-width': 2.2 } },
        { selector: 'node.down', style: { 'border-width': 2.2, 'border-color': '#9A7B17' } },
        { selector: 'node.sel', style: { 'border-width': 4, 'border-color': '#D4AF37', 'border-style': 'solid' } },
        { selector: 'edge.pathe', style: { 'line-color': '#8C2F2B', 'target-arrow-color': '#8C2F2B', width: 3.5, opacity: 1 } },
        { selector: 'node.pathn', style: { 'border-width': 3.5, 'border-color': '#8C2F2B' } },
      ],
      layout: layoutOpts(),
    })
    instance.on('tap', 'node', (ev) => onSelectRef.current(ev.target.id()))
    instance.on('tap', (ev) => { if (ev.target === instance) onSelectRef.current(null) })
    cy.current = instance
    if (import.meta.env.DEV) (window as unknown as { __cy?: Core }).__cy = instance   // test hook for the e2e smoke script
    const ro = new ResizeObserver(() => { instance.resize(); if (!instance.scratch('touched')) { if (layout === 'tiered') instance.layout(layoutOpts()).run(); else instance.fit(undefined, 30) } })
    const touch = () => instance.scratch('touched', true)
    box.current.addEventListener('wheel', touch, { passive: true })
    box.current.addEventListener('pointerdown', touch)
    ro.observe(box.current)
    return () => { ro.disconnect(); instance.destroy(); cy.current = null }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [graph])

  // layout switch
  useEffect(() => { cy.current?.layout(layoutOpts()).run() }, [layout]) // eslint-disable-line react-hooks/exhaustive-deps

  // data: scenario status per node
  useEffect(() => {
    const c = cy.current; if (!c) return
    c.batch(() => c.nodes().forEach((n) => {
      const imp = impacts.get(n.id())
      n.data('status', imp?.status ?? 'unaffected'); n.data('dis', imp ? imp.final_disruption : 0)
    }))
  }, [impacts, graph])

  // filtering + financial toggle
  useEffect(() => {
    const c = cy.current; if (!c) return
    c.batch(() => {
      c.nodes().forEach((n) => { n.style('display', visible.has(n.id()) ? 'element' : 'none') })
      c.edges('.fin').style('display', showFinancial ? 'element' : 'none')
    })
  }, [visible, showFinancial, graph])

  // highlight
  useEffect(() => {
    const c = cy.current; if (!c) return
    c.batch(() => {
      c.elements().removeClass('faded up down sel pathn pathe')
      if (!selectedId || !c.getElementById(selectedId).nonempty()) return
      const up = walk(graph, selectedId, 'up'); const down = walk(graph, selectedId, 'down')
      c.elements().addClass('faded')
      const reveal = (ids: Map<string, number>, eids: Set<string>, cls: string) => {
        ids.forEach((_, id) => c.getElementById(id).removeClass('faded').addClass(cls))
        eids.forEach((id) => c.getElementById(id).removeClass('faded').addClass(cls))
      }
      reveal(up.nodes, up.edges, 'up'); reveal(down.nodes, down.edges, 'down')
      c.getElementById(selectedId).removeClass('up down').addClass('sel')
      if (pathIds.length > 1) {
        pathIds.forEach((id, i) => {
          c.getElementById(id).removeClass('faded').addClass('pathn')
          if (i > 0) c.edges().filter((e) => e.source().id() === pathIds[i - 1] && e.target().id() === id).removeClass('faded').addClass('pathe')
        })
      }
    })
  }, [selectedId, pathIds, graph])

  return <div ref={box} className="h-full w-full" role="application" aria-label="Interactive supply-chain graph" data-testid="graph-canvas" />
})
export default GraphView
