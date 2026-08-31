// CJK 衬线网页字体（vite-plugin-font，配置见 vite.config.ts）。
// 必须通过异步 import 加载：全量分包会生成数百条 @font-face，
// 进主 CSS 包会拖慢渲染阻塞样式并挤占 PWA 预缓存预算；拆成异步
// chunk 后由 main.tsx 动态引入，首屏先用系统字体渲染，字体分包
// 按需到达后换装。
// 黑体（sans）不走网页字体：Noto Sans SC 的 600/700 字重明显重于
// macOS 苹方等系统黑体，接管 UI 中文后粗体观感发黑，已回退系统字体。
import "./assets/fonts/NotoSerifSC-VF.ttf";
