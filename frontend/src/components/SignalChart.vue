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
        color: "#000",
      },
      color: ["#2563eb", "#0f766e", "#7c3aed", "#c2410c", "#0891b2", "#be185d"],
      tooltip: {
        trigger: "axis",
        textStyle: { fontSize: 16, color: "#000" },
        backgroundColor: "#fff",
        borderColor: "#ddd",
        valueFormatter: (v: any) => `${Number(v).toFixed(3)} mV`,
      },
      legend: {
        data: names,
        top: 4,
        textStyle: { fontSize: 14, color: "#000" },
      },
      grid: { left: 65, right: 35, top: 50, bottom: 80 },
      xAxis: {
        type: "value",
        name: "秒",
        nameTextStyle: { fontSize: 14, color: "#000" },
        axisLabel: { fontSize: 14, color: "#000" },
        axisLine: { lineStyle: { color: "#9aa9bd" } },
        axisTick: { lineStyle: { color: "#9aa9bd" } },
        min: 0,
        max: 10,
        splitLine: { lineStyle: { color: "#e9eff7" } },
      },
      yAxis: {
        type: "value",
        name: "mV",
        nameTextStyle: { fontSize: 14, color: "#000" },
        axisLabel: { fontSize: 14, color: "#000" },
        axisLine: { lineStyle: { color: "#9aa9bd" } },
        axisTick: { lineStyle: { color: "#9aa9bd" } },
        scale: true,
        splitLine: { lineStyle: { color: "#e9eff7" } },
      },
      dataZoom: [
        { type: "inside" },
        {
          type: "slider",
          bottom: 10,
          backgroundColor: "#fff",
          fillerColor: "rgba(37,99,235,.10)",
          borderColor: "#d0dff1",
          textStyle: { color: "#000", fontSize: 14 },
          dataBackground: {
            lineStyle: { color: "#8cace0" },
            areaStyle: { color: "#edf3fc" },
          },
          selectedDataBackground: {
            lineStyle: { color: "#2563eb" },
            areaStyle: { color: "#dbeafe" },
          },
          handleStyle: { color: "#fff", borderColor: "#60a5fa" },
          moveHandleStyle: { color: "#93c5fd" },
          emphasis: {
            handleStyle: { color: "#eff6ff", borderColor: "#2563eb" },
            moveHandleStyle: { color: "#2563eb" },
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
