import { LineChart } from 'echarts/charts'
import {
  AxisPointerComponent,
  GridComponent,
  TooltipComponent
} from 'echarts/components'
import {
  graphic,
  init,
  use,
  type EChartsCoreOption
} from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'

import type {
  MeasurementRoleDefinition,
  MeasurementTimelineSnapshot
} from './measurementTimeline'

use([
  LineChart,
  GridComponent,
  TooltipComponent,
  AxisPointerComponent,
  CanvasRenderer
])

type ChartRole = MeasurementRoleDefinition & { label: string }
export type MeasurementChart = ReturnType<typeof init>

function seriesOption(role: ChartRole) {
  return {
    name: role.label,
    type: 'line',
    yAxisIndex: role.yAxisIndex,
    data: [],
    smooth: true,
    symbol: 'none',
    lineStyle: { color: role.color, width: role.lineWidth },
    areaStyle: role.area
      ? {
          color: new graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: 'rgba(17,18,20,0.16)' },
            { offset: 1, color: 'rgba(17,18,20,0)' }
          ])
        }
      : undefined
  }
}

export function createMeasurementChart(
  container: HTMLElement,
  roles: ChartRole[]
): MeasurementChart {
  const chart = init(container)
  const option: EChartsCoreOption = {
    backgroundColor: 'transparent',
    animationDuration: 320,
    grid: { top: 12, right: 12, bottom: 6, left: 36 },
    tooltip: {
      trigger: 'axis',
      backgroundColor: 'rgba(244,243,239,0.97)',
      borderColor: '#111214',
      borderWidth: 1,
      padding: [6, 8],
      textStyle: {
        color: '#111214',
        fontSize: 9,
        fontFamily: 'JetBrains Mono, monospace'
      },
      axisPointer: { lineStyle: { color: '#111214', width: 1 } }
    },
    xAxis: {
      type: 'category',
      data: [],
      boundaryGap: false,
      axisLine: { lineStyle: { color: '#c9c6c0' } },
      axisTick: { show: false },
      axisLabel: { show: false },
      splitLine: { show: false }
    },
    yAxis: [
      {
        type: 'value',
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: {
          color: '#77746d',
          fontSize: 7,
          fontFamily: 'JetBrains Mono, monospace'
        },
        splitLine: { lineStyle: { color: '#dedbd5', type: 'dashed' } }
      },
      {
        type: 'value',
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: { show: false },
        splitLine: { show: false }
      }
    ],
    series: roles.map(seriesOption)
  }
  chart.setOption(option)
  return chart
}

export function applyMeasurementRoles(
  chart: MeasurementChart,
  roles: ChartRole[]
) {
  chart.setOption({
    series: roles.map((role) => ({ name: role.label }))
  })
}

export function updateMeasurementChart(
  chart: MeasurementChart,
  snapshot: MeasurementTimelineSnapshot
) {
  chart.setOption({
    xAxis: { data: snapshot.times },
    series: snapshot.series.map((series) => ({
      name: series.label,
      data: series.data
    }))
  })
}
