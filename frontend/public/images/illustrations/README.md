# LambChat 场景插画

使用内置 imagegen 生成，以 `../lamb.webp` 为角色参考；保存为 384×384 透明 PNG，原有头像未修改。由 `SceneIllustration` 统一控制尺寸与明暗主题边缘对比。插画与回退图片均为静态，不引入循环动效。

生成提示词共同约束：

> Production UI spot illustration derived faithfully from the LambChat lamb avatar reference. Same cream wool tuft, floppy ears, tiny black eyes, warm blush, charcoal hand-drawn outline. Restrained flat warm ivory and muted sage colors, clean hand-drawn illustration, no text, no decorative sparkles, no background, true transparent alpha, generous padding, centered square composition, readable at 96px. Preserve the reference character identity.

场景提示词：

- `lamb-avatar.png`：内置 ImageGen，以 `lamb-welcome.png` 为参考生成的纯头部特写。只有圆脸、羊毛和双耳，无脖子、身体、四肢或道具；保留奶油白、粉色脸颊与棕色描边。头部占满方形画布，透明底、静态，适合 32–44px 头像，深浅色共用。
- `lamb-welcome.png`：Full small lamb sitting and raising one small paw to greet the user, warm calm expression.
- `lamb-reading.png`：Full small lamb sitting, holding an open book and reading attentively.
- `lamb-files.png`：Full small lamb sitting beside a muted sage folder, gently placing one cream paper into it.
- `lamb-message.png`：Full small lamb sitting, gently holding a small muted sage envelope with both paws, attentive friendly expression.
- `lamb-notification.png`：内置 ImageGen 图生图，以 `lamb-avatar.png` 和 `lamb-message.png` 为参考。小羊头部从浅鼠尾草绿信封后探出，两只小蹄自然搭在信封上缘；没有躯干或腿。保留奶油白羊毛、粉色脸颊、柔和棕色描边，表情放松、头部微倾。透明底，无铃铛、缎带、角标或装饰符号；192×192 静态 PNG，用于 44px 通知插图，深浅色共用。

## 面板专属头像（2026-09-30）

使用内置 ImageGen，以 `lamb-avatar.png` 为品牌参考逐张生成，保留原生成文件；交付素材为 `lamb-panel-*.png`，192×192 透明 PNG。桌面页头显示 48px，定制工具栏 48px，手机导航标题 28px。复用 `SceneIllustration` 的装饰语义、加载回退和主题处理。

共同提示词：

> Use case: stylized-concept. ONE production UI avatar for LambChat panel. Reference image is exact brand/style: round cream lamb face, scalloped wool, floppy ears, dark brown outline, tiny black eyes, peach blush. Preserve identity. New close-up head and tiny paws portrait with the scene below. Refined flat hand-drawn illustration, ivory, muted sage and terracotta, thick clean outlines. Head occupies upper two thirds, prop at lower right, fills 88% square canvas. Readable at 48px. True transparent alpha background. No text/letters, background circle, tile, gradients, sparkles, ground or shadow. No full body.

场景补充：

- `persona`: terracotta artist beret and small theatrical half-mask, conveying different personas.
- `skills`: holding a simple wooden pencil and small open sage notebook, capable learner.
- `marketplace`: holding a small sage shopping bag with a tiny terracotta tag, friendly shopkeeper.
- `files`: holding a sage tabbed folder with one cream paper peeking out, organized archivist.
- `bookmarks`: holding a closed sage book with a large terracotta ribbon bookmark over its cover, treasured reading.
- `team`: two close friendly lamb heads together, one wearing a sage neckerchief, conveying a coordinated team; two heads only.
- `memory`: wearing small round spectacles, holding one sage index card with a terracotta heart symbol, thoughtful memory keeper.
- `notifications`: gently holding a small warm ochre handbell, attentive messenger.
- `feedback`: holding a terracotta pencil over a sage speech bubble shaped notepad, listening expression.
- `schedule`: holding a round sage alarm clock with simple two hands and no numerals, reliable planner.
- `usage`: holding a sage clipboard showing three simple ascending terracotta bars, thoughtful analyst.
- `mcp`: joining two chunky sage connector plugs in its paws, integrations engineer.
- `users`: holding a sage identification badge bearing a small lamb silhouette, welcoming administrator.
- `roles`: holding a muted sage shield with one simple cream keyhole, calm guardian.
- `agents`: wearing a small sage headset with a microphone, attentive helpful assistant.
- `models`: holding a single sage microchip with thick short pins and a cream center, curious AI specialist.
- `settings`: holding a small sage cogwheel and terracotta-handled screwdriver, careful technician.
- `channels`: holding a sage paper airplane beside its cheek, friendly communication messenger.
