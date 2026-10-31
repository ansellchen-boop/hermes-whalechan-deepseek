#!/usr/bin/env bash
# 会话退出检查：临时工件（只读，不删任何东西）。
#
# 会话退出五条件 = 构建通过 / 测试通过 / 进度已记录 / 无临时工件 / 启动路径可用。
# 前两条由项目自己的验证命令兜着，第三条是 PROGRESS/ROADMAP，「无临时工件」最容易被漏掉
# —— 它此前靠记性，而记性每个会话清零。
#
# 用法：
#   bash check-session-exit.sh                        # 默认查脚本所在仓：<脚本目录>/..
#   bash check-session-exit.sh --repo /path/to/repo   # 查指定仓（从 skill 目录直接调时用）
#   bash check-session-exit.sh --remote qq:/root/qq-bridge   # 额外查远端（可重复）
#
# 退出码：0 干净 / 1 有残留 / 2 参数错
#
# 接进项目：放到仓库 scripts/ 下，在验证命令里挂一步
#   step "会话退出（临时工件）"; bash scripts/check-session-exit.sh || fail=1
# 顺序上的坑：存量没清干净之前别挂默认档 —— 挂上去就是个永远红的检查，红几次就没人看了。
set -uo pipefail

REMOTES=()
REPO=""
while [ $# -gt 0 ]; do
  case "$1" in
    --remote)
      shift
      if [ $# -eq 0 ]; then echo "--remote 后面要跟 host:/path" >&2; exit 2; fi
      REMOTES+=("$1"); shift ;;
    --repo)
      shift
      if [ $# -eq 0 ]; then echo "--repo 后面要跟仓库路径" >&2; exit 2; fi
      REPO="$1"; shift ;;
    -h|--help) awk 'NR>1 && /^set -uo/{exit} NR>1{print}' "$0"; exit 0 ;;
    *) echo "未知参数：$1（试 --help）" >&2; exit 2 ;;
  esac
done

# 这些模式定义了两处（本地数组 / 远端字符串），改的时候一起改。
FIND_EXPR=( -name '*.tmp.js' -o -name '*.tmp.mjs' -o -name '*.tmp.md' -o -name '*.tmp.log' \
            -o -name '*.bak[0-9]-*' -o -name '*.orig' -o -name '*.rej' \
            -o -name '.DS_Store' -o -name 'npm-debug.log*' -o -name 'debug-*.log' )

fail=0

report() {
  local label="$1" list="$2"
  if [ -z "$list" ]; then
    echo "✓ $label 无临时工件"
    return 0
  fi
  local n
  n=$(printf '%s\n' "$list" | wc -l)
  echo "✗ $label 有 $n 个临时工件："
  printf '%s\n' "$list" | sed 's/^/   /'
  echo "   清掉时给显式路径列表：rm -f -- ./a ./b ./c"
  echo "   （别用 find -delete / find -exec rm：没有复核点，也会撞上执行层的批量删除拦截）"
  echo "   这些文件不在 git 索引里时，历史里通常还取得到：git log --all --oneline -- <文件>"
  fail=1
}

# 本仓：默认脚本所在仓；--repo 指定别的（从 skill 目录直接调时用）
if [ -n "$REPO" ]; then
  here=$(cd "$REPO" 2>/dev/null && pwd) || { echo "✗ --repo 路径不存在：$REPO" >&2; exit 2; }
else
  here=$(cd "$(dirname "$0")/.." && pwd)
fi
# node_modules 必须剪掉：第三方包自带 *.tmp.mjs（如 js-yaml 的 index_vite_proxy.tmp.mjs），
# 假阳性报几次，这条检查就没人看了。
local_list=$( cd "$here" && find . \( -name .git -o -name node_modules \) -prune -o \( "${FIND_EXPR[@]}" \) -print 2>/dev/null \
              | sed 's|^\./||' | sort )
report "本仓 $here" "$local_list"

# 远端（可选）
for target in "${REMOTES[@]:-}"; do
  [ -z "$target" ] && continue
  host=${target%%:*}; rdir=${target#*:}
  if [ "$host" = "$target" ] || [ -z "$rdir" ]; then
    echo "✗ --remote 格式错了：$target（要 host:/path）" >&2; fail=1; continue
  fi
  if ! ssh -o ConnectTimeout=8 -o BatchMode=yes "$host" true 2>/dev/null; then
    echo "✗ $host 连不上，这一侧没查成（不是干净）"
    fail=1; continue
  fi
  remote_list=$( ssh -o ConnectTimeout=8 "$host" "cd '$rdir' && find . \\( -name .git -o -name node_modules \\) -prune -o \\( -name '*.tmp.js' -o -name '*.tmp.mjs' -o -name '*.tmp.md' -o -name '*.tmp.log' -o -name '*.bak[0-9]-*' -o -name '*.orig' -o -name '*.rej' -o -name '.DS_Store' -o -name 'npm-debug.log*' -o -name 'debug-*.log' \\) -print 2>/dev/null | sed 's|^\\./||' | sort" )
  report "远端 $host:$rdir" "$remote_list"
done

if [ "$fail" -eq 0 ]; then
  echo "✓ 会话退出检查（临时工件）通过"
else
  echo "✗ 会话退出检查（临时工件）失败"
fi
exit "$fail"
