/// <reference types="vite/client" />
/// <reference types="vite-plugin-font/src/font" />

declare module "@lobehub/icons-static-svg/icons/*.svg?url" {
  const src: string;
  export default src;
}

declare module "*.mjs?url" {
  const src: string;
  export default src;
}
