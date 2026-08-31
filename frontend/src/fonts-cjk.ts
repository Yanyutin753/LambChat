// CJK 网页字体（vite-plugin-font，配置见 vite.config.ts）。
// 必须通过异步 import 加载：全量分包会生成约 660 条 @font-face
// （~200KB CSS），进主 CSS 包会拖慢渲染阻塞样式并挤占 PWA 预缓存
// 预算；拆成异步 chunk 后由 main.tsx 动态引入，首屏先用系统字体渲染，
// 字体分包按需到达后换装。
import "./assets/fonts/NotoSansSC-VF.ttf";
import "./assets/fonts/NotoSerifSC-VF.ttf";
