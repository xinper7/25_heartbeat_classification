import axios from "axios";
import { ElMessage } from "element-plus";

export const api = axios.create({ baseURL: "/api/v1", timeout: 45000 });
api.interceptors.request.use((config) => {
  const token = sessionStorage.getItem("ecg-token");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});
api.interceptors.response.use(
  (response) => response,
  (error) => {
    const message =
      error.response?.data?.msg ||
      (error.code === "ECONNABORTED"
        ? "请求超时，请先查询检查状态，避免重复提交。"
        : "服务暂时无法连接，请检查后端运行状态。");
    ElMessage.error(message);
    if (
      error.response?.status === 401 &&
      !error.config?.url?.includes("/auth/login")
    ) {
      sessionStorage.removeItem("ecg-token");
      window.dispatchEvent(new Event("ecg-logout"));
    }
    return Promise.reject(error);
  },
);

export async function get(path: string, params?: Record<string, unknown>) {
  return (await api.get(path, { params })).data.result;
}
export async function post(path: string, data?: unknown) {
  return (await api.post(path, data)).data.result;
}
const downloads = new Set<string>();
export async function download(path: string, name: string, params?: Record<string, unknown>) {
  if (downloads.has(path)) { ElMessage.info("文件正在生成，请稍候"); return; }
  downloads.add(path);
  ElMessage.info("正在生成下载文件…");
  try {
  const response = await api.get(path, { responseType: "blob", params });
  const url = URL.createObjectURL(response.data);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  // Let the browser consume large reports before releasing their blob URL.
  setTimeout(() => URL.revokeObjectURL(url), 60000);
  ElMessage.success("文件已生成，已发起下载");
  } finally { downloads.delete(path); }
}
