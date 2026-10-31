# hermes-whalechan-deepseek —— 一个入口跑完全部验证
#
# 用途：改完任何东西，跑 `make check`。它不碰网络、不改配置、秒级返回。
# 需要写配置的动作（apply.py 不带 --check）刻意不放进 check，
# 因为那是「部署」不是「验证」。

PY       ?= python3
VENV_PY  := $(HOME)/.hermes/hermes-agent/venv/bin/python

.PHONY: help check test syntax apply-check audit drift probe lint typecheck

help:
	@echo "make check       全套验证 = syntax + test + apply-check + probe（默认该跑的）"
	@echo "make test        单元测试（纯逻辑，不走网络）"
	@echo "make syntax      语法编译检查（compileall）"
	@echo "make apply-check 仓库 vs 已安装的人设/插件是否一致（只读）"
	@echo "make audit       指令审计：三处 AGENTS.md 的尺寸/三件/死链/陈旧度（不阻塞 check）"
	@echo "make drift       人设漂移曲线 + 节拍骰 A/B（读 state.db 和 roll-log）"
	@echo "make probe       闸门矩阵探针（9 个用例，临时 HERMES_HOME，不碰真配置）"
	@echo "make lint        ruff（未装则跳过并提示）"
	@echo "make typecheck   mypy（未装则跳过并提示）"

check: syntax test apply-check probe
	@echo "✓ 全部通过"

syntax:
	@$(PY) -m compileall -q plugins scripts tests && echo "✓ syntax"

test:
	@$(PY) -m unittest discover -s tests

apply-check:
	@test -x $(VENV_PY) || { echo "找不到 Hermes venv: $(VENV_PY)"; exit 1; }
	@$(VENV_PY) apply.py --check

audit:
	@test -x $(VENV_PY) || { echo "找不到 Hermes venv: $(VENV_PY)"; exit 1; }
	@$(VENV_PY) scripts/audit_instructions.py

drift:
	@test -x $(VENV_PY) || { echo "找不到 Hermes venv: $(VENV_PY)"; exit 1; }
	@$(VENV_PY) scripts/measure_persona_drift.py

probe:
	@test -x $(VENV_PY) || { echo "找不到 Hermes venv: $(VENV_PY)"; exit 1; }
	@$(VENV_PY) scripts/probe_gates.py

lint:
	@if command -v ruff >/dev/null 2>&1; then \
		ruff check plugins scripts tests; \
	else \
		echo "跳过 lint：未安装 ruff（python3 -m pip install --user ruff）"; \
	fi

typecheck:
	@if $(PY) -c "import mypy" >/dev/null 2>&1; then \
		$(PY) -m mypy plugins/whalechan/chance.py; \
	else \
		echo "跳过 typecheck：未安装 mypy（python3 -m pip install --user mypy）"; \
	fi
