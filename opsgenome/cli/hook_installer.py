"""Shell Hook Installer.

Installs or removes OpsGenome shell integration hooks into ~/.zshrc or ~/.bashrc.
"""

from __future__ import annotations

import os
from pathlib import Path


class HookInstaller:
    """Manages shell hook activation."""

    HOOK_BLOCK_ZSH = """
# >>> OpsGenome Shell Integration Hook >>>
if [ -f "$HOME/.opsgenome/hooks/opsgenome.zsh" ]; then
    source "$HOME/.opsgenome/hooks/opsgenome.zsh"
fi
# <<< OpsGenome Shell Integration Hook <<<
"""

    HOOK_BLOCK_BASH = """
# >>> OpsGenome Shell Integration Hook >>>
if [ -f "$HOME/.opsgenome/hooks/opsgenome.bash" ]; then
    source "$HOME/.opsgenome/hooks/opsgenome.bash"
fi
# <<< OpsGenome Shell Integration Hook <<<
"""

    @classmethod
    def install(cls) -> tuple[bool, str]:
        """Copy hook files to ~/.opsgenome/hooks and append source block to shell rc."""
        home = Path.home()
        ops_hooks_dir = home / ".opsgenome" / "hooks"
        ops_hooks_dir.mkdir(parents=True, exist_ok=True)

        # Source files
        src_dir = Path(__file__).resolve().parent.parent / "hooks"

        zsh_src = src_dir / "opsgenome.zsh"
        bash_src = src_dir / "opsgenome.bash"

        if zsh_src.exists():
            (ops_hooks_dir / "opsgenome.zsh").write_text(zsh_src.read_text())
        if bash_src.exists():
            (ops_hooks_dir / "opsgenome.bash").write_text(bash_src.read_text())

        # Determine user shell
        shell = os.environ.get("SHELL", "")
        installed_files: list[str] = []

        if "zsh" in shell:
            zshrc = home / ".zshrc"
            content = zshrc.read_text() if zshrc.exists() else ""
            if "OpsGenome Shell Integration Hook" not in content:
                with open(zshrc, "a") as f:
                    f.write(cls.HOOK_BLOCK_ZSH)
                installed_files.append(str(zshrc))
        elif "bash" in shell:
            bashrc = home / ".bashrc"
            content = bashrc.read_text() if bashrc.exists() else ""
            if "OpsGenome Shell Integration Hook" not in content:
                with open(bashrc, "a") as f:
                    f.write(cls.HOOK_BLOCK_BASH)
                installed_files.append(str(bashrc))

        if installed_files:
            return True, f"OpsGenome hooks installed in: {', '.join(installed_files)}. Run 'source {installed_files[0]}' to activate."
        return True, "OpsGenome hooks already installed or ready in ~/.opsgenome/hooks"
