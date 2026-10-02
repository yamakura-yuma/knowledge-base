# PR のゲート。人もエージェントも Actions も `just ci` だけを打つ。
# 型は https://github.com/yamakura-yuma/dotfiles/blob/main/docs/gates.md
# 静的チェックだけで、作業ツリーは変えない。ツールが無ければ黙って飛ばさず落ちる。

set shell := ["bash", "-euo", "pipefail", "-c"]

# markdownlint-cli2 は npx が取る（Actions の runner にも node が入っている）
markdownlint := "markdownlint-cli2@0.18.1"

ci: lint links

# markdown の lint。規則は .markdownlint-cli2.yaml
lint:
    git ls-files -z --cached --others --exclude-standard '*.md' | xargs -0 npx --yes {{markdownlint}}

# 内部リンクの切れ（外部リンクは見ない）
links:
    python3 docs/check_links.py
