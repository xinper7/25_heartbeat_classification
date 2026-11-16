import { createRouter, createWebHistory } from "vue-router";
const Empty = { template: "<span />" };
export const router = createRouter({
  history: createWebHistory(),
  routes: [
    ...[
      "dashboard",
      "agent",
      "patients",
      "signal",
      "image",
      "studies",
      "review",
      "jobs",
      "models",
      "admin",
    ].map((path) => ({ path: `/${path}`, name: path, component: Empty })),
    { path: "/:pathMatch(.*)*", redirect: "/dashboard" },
  ],
});
