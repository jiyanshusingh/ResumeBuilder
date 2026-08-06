def latex_escape(s: str) -> str:
    """Escape special LaTeX characters."""
    if s is None:
        return ""
    s = str(s)
    s = s.replace("\\", "\\textbackslash ")
    s = s.replace("$", "\\$")
    s = s.replace("&", "\\&")
    s = s.replace("%", "\\%")
    s = s.replace("#", "\\#")
    s = s.replace("_", "\\_")
    s = s.replace("{", "\\{")
    s = s.replace("}", "\\}")
    s = s.replace("~", "\\textasciitilde ")
    s = s.replace("^", "\\textasciicircum ")
    return s