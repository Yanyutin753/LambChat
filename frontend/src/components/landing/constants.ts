export const SECTION_IDS = [
  "interface",
  "features",
  "architecture",
  "dashboard",
  "responsive",
];

export const SECTION_ROUTE_BY_ID: Record<string, string> = {
  interface: "/interface",
  features: "/features",
  architecture: "/architecture",
  dashboard: "/dashboard",
  responsive: "/responsive",
};

export const SECTION_ID_BY_ROUTE: Record<string, string> = Object.fromEntries(
  Object.entries(SECTION_ROUTE_BY_ID).map(([id, route]) => [route, id]),
);

export const NAV_ITEMS = [
  { id: "interface", labelKey: "sectionLabelInterface" },
  { id: "features", labelKey: "sectionLabelFeatures" },
  { id: "architecture", labelKey: "sectionLabelArchitecture" },
  { id: "dashboard", labelKey: "sectionLabelDashboard" },
];
