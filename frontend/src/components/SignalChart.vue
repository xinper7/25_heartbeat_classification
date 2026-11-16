<template>
  <div
    ref="host"
    class="signal-chart"
    :aria-label="'心电信号波形图，导联：' + (selected.length ? selected : ['II']).join('、')"
  ></div>
</template>
<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from "vue";
import * as echarts from "echarts/core";
import { LineChart } from "echarts/charts";
import {
  GridComponent,
  TooltipComponent,
  DataZoomComponent,
  LegendComponent,
} from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
echarts.use([
  LineChart,
  GridComponent,
  TooltipComponent,
  DataZoomComponent,
  LegendComponent,
  CanvasRenderer,
]);
const props = defineProps<{ data: any; selected: string[] }>();
const host = ref<HTMLElement>();
let chart: echarts.ECharts | undefined;
let observer: ResizeObserver | undefined;
let resizeFrame: number | undefined;
let observedWidth = 0;
let observedHeight = 0;
function render() {
  if (!chart || !props.data) return;
  const names = props.selected.length ? props.selected : ["II"];
  chart.setOption(
    {
      animation: false,
      textStyle: {
        fontSize: 14,
        fontFamily: "Microsoft YaHei, sans-serif",
        color: "#7898b5",
      },
      color: ["#42a8da", "#6d91db", "#ae98d8", "#d5a34d", "#4aaf9a", "#cc879f"],
      tooltip: {
        trigger: "axis",
        textStyle: { fontSize: 16, color: "#7898b5" },
        backgroundColor: "#fbfdff",
        borderColor: "#d9e8f4",
        valueFormatter: (v: any) => `${Number(v).toFixed(3)} mV`,
      },
      legend: {
        data: names,
        top: 4,
        textStyle: { fontSize: 14, color: "#7898b5" },
      },
      grid: { left: 65, right: 35, top: 50, bottom: 80 },
      xAxis: {
        type: "value",
        name: "秒",
        nameTextStyle: { fontSize: 14, color: "#7898b5" },
        axisLabel: { fontSize: 14, color: "#7898b5" },
        axisLine: { lineStyle: { color: "#b9cfe1" } },
        axisTick: { lineStyle: { color: "#b9cfe1" } },
        min: 0,
        max: 10,
        splitLine: { lineStyle: { color: "#e8f1f8" } },
      },
      yAxis: {
        type: "value",
        name: "mV",
        nameTextStyle: { fontSize: 14, color: "#7898b5" },
        axisLabel: { fontSize: 14, color: "#7898b5" },
        axisLine: { lineStyle: { color: "#b9cfe1" } },
        axisTick: { lineStyle: { color: "#b9cfe1" } },
        scale: true,
        splitLine: { lineStyle: { color: "#e8f1f8" } },
      },
      dataZoom: [
        { type: "inside" },
        {
          type: "slider",
          bottom: 10,
          backgroundColor: "#fbfdff",
          fillerColor: "rgba(37,99,235,.10)",
          borderColor: "#cce1f0",
          textStyle: { color: "#7898b5", fontSize: 14 },
          dataBackground: {
            lineStyle: { color: "#8cace0" },
            areaStyle: { color: "#edf7fd" },
          },
          selectedDataBackground: {
            lineStyle: { color: "#42a8da" },
            areaStyle: { color: "#d9effa" },
          },
          handleStyle: { color: "#fbfdff", borderColor: "#60a5fa" },
          moveHandleStyle: { color: "#93c5fd" },
          emphasis: {
            handleStyle: { color: "#e5f5fe", borderColor: "#42a8da" },
            moveHandleStyle: { color: "#42a8da" },
          },
        },
      ],
      series: names.map((name, index) => ({
        name,
        type: "line",
        showSymbol: false,
        lineStyle: {
          width: 1.8,
          type: index < 6 ? "solid" : "dashed",
        },
        data: props.data.times.map((t: number, i: number) => [
          t,
          props.data.values[props.data.leads.indexOf(name)][i],
        ]),
      })),
    },
    true,
  );
}
onMounted(() => {
  chart = echarts.init(host.value!);
  observer = new ResizeObserver(([entry]) => {
    if (!entry) return;
    const { width, height } = entry.contentRect;
    if (width === observedWidth && height === observedHeight) return;
    observedWidth = width;
    observedHeight = height;
    if (resizeFrame !== undefined) cancelAnimationFrame(resizeFrame);
    // Resize on the next frame to avoid changing layout during observer delivery.
    resizeFrame = requestAnimationFrame(() => {
      resizeFrame = undefined;
      chart?.resize();
    });
  });
  observer.observe(host.value!);
  render();
});
watch(() => [props.data, props.selected], render, { deep: true });
onBeforeUnmount(() => {
  observer?.disconnect();
  if (resizeFrame !== undefined) cancelAnimationFrame(resizeFrame);
  chart?.dispose();
});
</script>
