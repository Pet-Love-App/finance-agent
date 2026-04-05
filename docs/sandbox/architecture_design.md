# Code Sandbox 架构设计文档

## 1. 现状评估结论
- 当前系统未集成代码沙箱安全执行环境。
- 未发现 Docker/WASM/Firecracker/V8 Isolate 的统一执行入口。
- 未发现 seccomp-BPF、Capabilities 降权、AppArmor/SELinux 策略接入。
- 未发现针对动态代码执行的审计链路与实时风险拦截。

## 2. 核心技术选型
- 主执行引擎: Docker 容器沙箱（已实现）。
- 预留扩展接口: `SandboxPolicy.technology` 支持 `docker/wasm/firecracker/v8` 兼容扩展。
- 原因:
  - 工程可落地性高，便于与现有 Python 调度系统融合。
  - 支持 cgroup 资源配额、seccomp、capabilities、只读根文件系统。

## 3. 资源限制策略
- CPU: `--cpus`，默认 `1.0`。
- 内存: `--memory`，默认 `512MB`。
- 进程数: `--pids-limit`，默认 `64`。
- 磁盘: 通过只读根文件系统 + 独立临时挂载目录控制写入范围。
- 网络: 默认 `--network none`，阻断外联。
- 熔断机制: `CircuitBreaker` 在窗口期失败次数超阈值时开启熔断。

## 4. 安全隔离规范
- 系统调用白名单: `SandboxPolicy.syscall_whitelist` + 运行时检查。
- seccomp-BPF: `agent/sandbox/profiles/seccomp-default.json`。
- Capabilities 降权: `--cap-drop ALL`。
- no-new-privileges: `--security-opt no-new-privileges:true`。
- AppArmor: `agent/sandbox/profiles/apparmor-sandbox.profile`。
- SELinux: 生产环境建议使用容器标签隔离（文档策略，按部署平台启用）。

## 5. 动态执行流程
1. 提交: `ExecutionRequest` 接收用户代码。
2. 静态扫描: `StaticSecurityScanner` 阻断高危模式。
3. 签名: `sign_code` 生成 `code_hash + signature`。
4. 沙箱启动: `DockerSandboxDriver.run` 按配额启动容器。
5. 运行时监控: 解析 `EVENT:*` 并进行风险判定。
6. 结果回收: 收集 stdout/stderr/telemetry。
7. 沙箱销毁: Docker `--rm` 自动清理容器。

## 6. 风险行为实时检测与拦截
- 文件系统越权: 拦截 `..`、`/etc`、`/proc` 路径事件。
- 网络外联: 监控到 network 事件即阻断。
- 子进程创建: process 事件触发阻断。
- 敏感 API: 命中 `os.system/subprocess/socket/eval/exec` 等关键词阻断。

## 7. 性能与扩容指标
- 冷启动目标: `<= 800ms`（以轻量镜像与预热池达成）。
- 并发目标: `1000` 实例（配合队列与多节点调度）。
- 扩容阈值: 当 `CPU 利用率 <= 80%` 时触发横向扩容（按需求定义实现为策略阈值）。

## 8. 高可用部署建议
- 多可用区: 控制面和执行面跨 AZ 部署。
- 故障转移: 健康检查 + 流量切换，目标 `<= 30s`。
- 备份目标: 审计日志与执行元数据 `RPO <= 5min`。

## 9. 审计与合规
- 日志字段:
  - 用户 ID
  - 代码哈希
  - 执行时长
  - 系统调用序列
  - 异常事件
- 存储:
  - `data/audit/sandbox_audit.jsonl`
  - 默认保留 180 天（`AuditLogger.retention_days`）。
