FixAtoms Studio — Windows 64 位便携版

启动
1. 将整个压缩包解压到一个可写的普通文件夹，例如桌面或 D 盘。
2. 双击 FixAtomsStudio.exe。
3. 无需安装 Python、Conda、Qt 或 ASE；运行无需联网。

请保留 FixAtomsStudio.exe 与 _internal 文件夹的相对位置。
整个 FixAtomsStudio 文件夹可以一起复制或移动，不能只复制 EXE。
不要在压缩包预览窗口中直接运行 EXE，请先完整解压。

使用
- “打开结构”读取 CIF、POSCAR / CONTCAR 或 XSD。
- “体验示例”载入内置 Cu(111) 示例；examples 文件夹提供三种输入格式。
- 点选 / 框选固定原子，Shift 框选解除；黑色网格叠加在彩色实心球外。
- “Ball 设置”通过周期表调整各元素的颜色和球直径。
- 六个标准视图、正交 / 透视、透视角度和深度雾化均可使用。
- 仅导出 POSCAR，保留原子顺序及 Selective dynamics 固定标记。
- F11 切换全屏；Ctrl+O 打开；Ctrl+S 导出；Ctrl+Z 撤销。

设置
保存的外观偏好写入 EXE 同目录的 ball_settings.json，迁移时可一并复制。
上、下视图按当前定义使用相同朝向；非正交晶胞保留真实夹角。

适用环境
Windows 10 / 11，64 位。需要系统支持 QtWebEngine / WebGL。
本便携包包含自定义图标和程序依赖，不需要连接原开发环境。

诊断（可选）
在 PowerShell 中执行：
  .\FixAtomsStudio.exe --self-test .\自检结果
会打开窗口，检查内置文件读取、3D 渲染、约束导出和视图操作，保存 report.json
与窗口截图后自动退出。普通使用直接双击 EXE 即可。
