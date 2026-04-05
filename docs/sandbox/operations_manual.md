# Code Sandbox 运维手册

## 1. 部署前检查
- 安装 Docker Engine。
- 启用 AppArmor/SELinux（按宿主机平台）。
- 配置环境变量:
  - `SANDBOX_SIGNING_KEY`
  - `AGENT_PROJECT_ROOT`（可选）

## 2. 启动与调用
- 任务模式:
  - `task_type = sandbox_exec`
  - payload 必填: `user_id`, `language`, `code`
- CLI 模式:
  - `python -m agent.sandbox.cli scan --code-file demo.py`
  - `python -m agent.sandbox.cli exec --user-id u1 --language python --code-file demo.py`

## 3. 监控指标
- `sandbox_execution_total`
- `sandbox_execution_denied_total`
- `sandbox_execution_blocked_total`
- `sandbox_circuit_breaker_open`
- `sandbox_duration_ms`

## 4. 故障处理
- Docker 不可用:
  - 检查 `docker info` 与 daemon 状态。
- 熔断开启:
  - 观察近 60s 失败率，排查镜像、策略和资源瓶颈。
- 日志写入失败:
  - 检查 `data/audit` 目录权限与磁盘空间。

## 5. 备份与恢复
- 审计日志每 5 分钟同步到对象存储。
- 恢复顺序:
  1) 恢复日志索引
  2) 恢复执行元数据
  3) 重放关键事件
