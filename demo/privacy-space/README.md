# Miloco 隐私空间动画演示

这是一个独立的本地演示页，用合成房间、匿名人物、设备状态和穿搭建议展示 Miloco 的结构化家庭状态。

它演示的是“隐私摘要状态 + 动画空间视图”，不是实时摄像头脱敏器。当前版本不访问真实摄像头、模型、音箱、1812 服务或私人家庭媒体。

## 当前能力

- Q 版空间布局：客厅、卧室、匿名人物和设备状态；
- 今日穿搭建议：只展示合成衣物名称；
- 隐私处理状态：合成单帧结果回放、固定摘要和临时帧清理状态；
- 纯 RGBA 合成帧遮挡：点击回放后对指定矩形做本地像素覆盖，并展示前后对比；
- 证据级别：已确认和有依据推断；
- 单元测试：成功清理、失败清理、低敏感度字段边界。
- 只读适配器契约：只有宿主明确给出的房间、匿名人数和穿搭摘要可进入演示；缺失事实保持未知，不从 capability 推断。

## 本地验证

在 E 盘 demo 目录安装本地依赖（不要使用 C 盘缓存）：

```powershell
$env:PNPM_STORE_DIR = "E:\\new_job\\10-AIProjects\\MilocoDev\\.pnpm-store"
$env:PNPM_CONFIG_CACHE_DIR = "E:\\new_job\\10-AIProjects\\MilocoDev\\.pnpm-cache"
pnpm install --offline --ignore-scripts
```

如果离线元数据缺失，使用仓库 `web` workspace 已安装的 runner 运行测试和构建，不要切换到 C 盘缓存：

```powershell
$env:NODE_PATH = "E:\\new_job\\10-AIProjects\\MilocoDev\\xiaomi-miloco-outfit-voice-vision\\web\\node_modules"
& "E:\\new_job\\10-AIProjects\\MilocoDev\\xiaomi-miloco-outfit-voice-vision\\web\\node_modules\\.bin\\vitest.cmd" run --config .\\vitest.config.ts
& "E:\\new_job\\10-AIProjects\\MilocoDev\\xiaomi-miloco-outfit-voice-vision\\web\\node_modules\\.bin\\vite.cmd" build --config .\\vite.config.ts
```

依赖安装完成后可运行：

```powershell
pnpm run typecheck
pnpm run build
pnpm test
pnpm run smoke:static
```

从已安装依赖的 web workspace 复用 Vitest：

```powershell
$env:NODE_PATH = "E:\new_job\10-AIProjects\MilocoDev\xiaomi-miloco-outfit-voice-vision\web\node_modules"
& "E:\new_job\10-AIProjects\MilocoDev\xiaomi-miloco-outfit-voice-vision\web\node_modules\.bin\vitest.cmd" run --config "E:\new_job\10-AIProjects\MilocoDev\xiaomi-miloco-outfit-voice-vision\demo\privacy-space\vitest.config.ts"
```

当前测试只使用合成临时文件，临时目录应放在 E 盘。2026-10-19 已通过内置浏览器完成桌面 1440×900 和手机 390×844 视口的真实渲染、回放点击及无横向溢出检查。
像素遮挡只针对代码内的合成 2×2 RGBA 示例，浏览器没有写入原始帧文件。`PrivacyFrameProcessor` 的文件清理是独立的本地测试契约；真实摄像头媒体清理仍由 Miloco 宿主契约承担。
`smoke:static` 只验证 production 包中的关键文案、敏感字段排除和响应式断点，不替代真实浏览器交互验收。

## 面试演示脚本

1. 展示“结构化空间视图”，说明画面没有原始家庭视频；
2. 展示匿名人物、设备在线状态和空间证据级别；
3. 点击“回放合成处理结果”，说明合成帧只在测试临时目录短暂存在；
4. 展示“临时帧已清理”和固定错误码边界；
5. 展示今日穿搭建议，说明建议来自确认库存的结构化状态；
6. 说明未来接入 Miloco 时使用只读 adapter，不直接读取摄像头、数据库或 owner 标识。

公开截图和视频只能使用合成数据。不要把家庭地址、人物照片、设备 ID、token、原始帧或模型原始回答放入公开材料。
