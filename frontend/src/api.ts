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
export async function download(path: string, name: string) {
  const response = await api.get(path, { responseType: "blob" });
  const url = URL.createObjectURL(response.data);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
