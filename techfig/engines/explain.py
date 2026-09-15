"""Explainer page assembler (techfig explain).

This module compiles markdown documents with embedded techfig diagrams into
standalone, self-contained interactive HTML explainer pages.

Front-matter and Reference Parsing:
- Front-matter is parsed using a minimal line-based YAML-ish parser (no PyYAML
  dependency). It supports 'title', 'subtitle', 'status', 'style', and 'refs'.
- References can be specified either:
    1. In the front-matter as a single-line JSON array:
       refs: [{"n": 1, "doi": "10.1038/...", "text": "Smith et al."}]
    2. Or anywhere in the document within a fenced ```refs [json] block.
- Prose citations [^N] are transformed into hyperlinks (<a href="#ref-N">).
- Section epistemic status markers (e.g. '> status: Active' following a heading)
  are converted to inline badges in the section heading.
- Diagrams are rendered inlined into <figure> elements. Static figures have
  their SVG IDs namespaced (fig{N}-). Interactive figures embed controls and
  bind into the unified __tf runtime (namespaced under __tf.figs[fig{N}]).
- If interactive figures are present, the runtime JS is embedded exactly once.
  No remote scripts or external CDNs are referenced.
"""
import copy
import json
import re
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from techfig.engines.interactive_svg import render_interactive_fragment, runtime_js
from techfig.engines.sketch_interpreter import render_from_spec
from techfig.styles.presets import get_style


def _parse_front_matter(text: str) -> Tuple[Dict[str, Any], str]:
    """Extract optional YAML-like front-matter (--- ... ---) and remainder body."""
    match = re.match(r"^---\r?\n(.*?)\r?\n---\r?\n", text, re.DOTALL)
    if not match:
        return {}, text

    fm_text = match.group(1)
    body = text[match.end():]
    meta: Dict[str, Any] = {}

    for line in fm_text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        k = k.strip()
        v = v.strip()
        if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
            v = v[1:-1]
        if k == "refs":
            try:
                meta["refs"] = json.loads(v)
            except Exception:
                meta["refs"] = []
        else:
            meta[k] = v

    return meta, body


def _extract_fenced_refs(body: str) -> Tuple[List[Dict[str, Any]], str]:
    """Extract fenced ```refs [json] blocks and return list of refs and cleaned body."""
    refs: List[Dict[str, Any]] = []
    pattern = re.compile(r"```refs(?:[ \t]+json)?[ \t]*\r?\n(.*?)\r?\n```", re.DOTALL)

    for m in pattern.finditer(body):
        content = m.group(1).strip()
        try:
            parsed = json.loads(content)
            if isinstance(parsed, list):
                refs.extend(parsed)
            elif isinstance(parsed, dict):
                refs.append(parsed)
        except Exception:
            pass

    cleaned_body = pattern.sub("", body)
    return refs, cleaned_body


def namespace_svg_ids(svg_text: str, prefix: str) -> str:
    """Namespace all id attributes and references (url(#id), href="#id") in SVG."""
    def_ids = set(re.findall(r'\bid=["\']([^"\']+)["\']', svg_text))
    unprefixed = [i for i in def_ids if not i.startswith(prefix)]
    unprefixed.sort(key=len, reverse=True)
    for old_id in unprefixed:
        new_id = f"{prefix}{old_id}"
        svg_text = re.sub(
            r'\bid=(["\'])' + re.escape(old_id) + r'\1',
            f'id=\\1{new_id}\\1',
            svg_text,
        )
        svg_text = re.sub(
            r'url\((["\']?)#' + re.escape(old_id) + r'\1\)',
            f'url(\\1#{new_id}\\1)',
            svg_text,
        )
        svg_text = re.sub(
            r'(href=["\']?)#' + re.escape(old_id) + r'(["\']?)',
            f'\\1#{new_id}\\2',
            svg_text,
        )
    return svg_text


def _process_section_status_badges(text: str) -> str:
    """Turn '> status: Value' lines after section headings into inline badges."""
    pattern = re.compile(
        r"(^#{1,6}\s+[^\r\n]+)\r?\n+(?:[ \t]*>[ \t]*status[ \t]*:[ \t]*([A-Za-z]+)[ \t]*(?:\r?\n|$))",
        re.MULTILINE,
    )

    def repl(m):
        heading = m.group(1).rstrip()
        status = m.group(2).strip()
        badge = f'<span class="tf-status tf-status-{status.lower()}">{status}</span>'
        return f"{heading} {badge}\n\n"

    return pattern.sub(repl, text)


def _process_citations(text: str) -> str:
    """Transform [^N] citations into links <a href="#ref-N" class="tf-cite">[N]</a>."""
    return re.sub(
        r"\[\^([a-zA-Z0-9_-]+)\]",
        r'<a href="#ref-\1" class="tf-cite">[\1]</a>',
        text,
    )


def _minimal_markdown(md_text: str) -> str:
    """Fallback markdown parser for basic formatting without external dependencies."""
    blocks = re.split(r"\n\s*\n", md_text.strip())
    html_blocks = []

    for block in blocks:
        block = block.strip()
        if not block:
            continue

        # If it's a preserved placeholder or HTML element, don't wrap in <p>
        if block.startswith("<!--") and block.endswith("-->"):
            html_blocks.append(block)
            continue
        if block.startswith("<figure") or block.startswith("<div") or block.startswith("<section"):
            html_blocks.append(block)
            continue

        # Heading
        m_head = re.match(r"^(#{1,6})\s+(.*)$", block, re.DOTALL)
        if m_head:
            level = len(m_head.group(1))
            content = _apply_inline_formatting(m_head.group(2).strip())
            html_blocks.append(f"<h{level}>{content}</h{level}>")
            continue

        # List
        lines = block.splitlines()
        if all(re.match(r"^[*-]\s+", ln.strip()) for ln in lines if ln.strip()):
            items = []
            for ln in lines:
                m_li = re.match(r"^[*-]\s+(.*)$", ln.strip())
                if m_li:
                    items.append(f"  <li>{_apply_inline_formatting(m_li.group(1))}</li>")
            html_blocks.append("<ul>\n" + "\n".join(items) + "\n</ul>")
            continue

        # Blockquote (standard)
        if all(ln.strip().startswith(">") for ln in lines if ln.strip()):
            bq_lines = [re.sub(r"^[ \t]*>[ \t]?", "", ln) for ln in lines]
            content = _apply_inline_formatting("\n".join(bq_lines))
            html_blocks.append(f"<blockquote>{content}</blockquote>")
            continue

        # Paragraph
        content = _apply_inline_formatting(block)
        html_blocks.append(f"<p>{content}</p>")

    return "\n".join(html_blocks)


def _apply_inline_formatting(text: str) -> str:
    """Apply bold, italics, inline code, links, and citations."""
    # Inline code
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    # Bold
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    # Italic
    text = re.sub(r"\*([^*]+)\*", r"<em>\1</em>", text)
    # Links [text](url)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', text)
    # Citations
    text = _process_citations(text)
    return text


def _to_html(md_text: str) -> str:
    """Convert markdown to HTML, using the `markdown` library if available."""
    try:
        import markdown
        return markdown.markdown(md_text)
    except ImportError:
        return _minimal_markdown(md_text)


def _css_vars(preset_name: str) -> str:
    """Generate CSS custom properties for the selected style preset."""
    st = get_style(preset_name)
    colors = st.get("colors", {})
    return (
        f'--tf-primary: {colors.get("primary", "#0072B2")};\n'
        f'--tf-bg: {colors.get("background", "#FFFFFF")};\n'
        f'--tf-fg: {colors.get("text", "#000000")};\n'
        f'--tf-accent: {colors.get("accent", "#009E73")};\n'
        f'--tf-muted: {colors.get("muted", "#888888")};\n'
        f'--tf-gray: #888888;'
    )


def render_explainer(
    markdown_text: str,
    base_dir: Optional[Path | str] = None,
) -> str:
    """Compile a markdown document with techfig specs into a self-contained HTML page.

    Args:
        markdown_text: Markdown source with optional front-matter and fenced blocks.
        base_dir: Base directory for resolving external spec or model files.

    Returns:
        Full self-contained HTML document string.
    """
    base_path = Path(base_dir).resolve() if base_dir else Path.cwd()
    meta, body = _parse_front_matter(markdown_text)

    # Combine refs from front-matter and any fenced ```refs blocks
    fenced_refs, body = _extract_fenced_refs(body)
    all_refs = list(meta.get("refs") or []) + fenced_refs

    # Process section status badges before figure extraction
    body = _process_section_status_badges(body)

    # Extract fenced techfig blocks and assemble figures
    fig_pattern = re.compile(
        r"```techfig(?:[ \t]+([^\r\n]*))?\r?\n(.*?)\r?\n```(?:[ \t]*\r?\n+[ \t]*Caption:[ \t]*([^\r\n]*))?",
        re.DOTALL,
    )

    figure_counter = 0
    figures_map: Dict[str, str] = {}
    model_scripts: List[str] = []
    bindings_scripts: List[str] = []

    def replace_figure(m: re.Match) -> str:
        nonlocal figure_counter
        figure_counter += 1
        fig_id = f"fig{figure_counter}"

        info_str = m.group(1).strip() if m.group(1) else ""
        raw_body = m.group(2).strip()
        caption = m.group(3).strip() if m.group(3) else None
        is_interactive = "interactive" in info_str.split()

        if raw_body.startswith("file:"):
            rel_file = raw_body.split("file:", 1)[1].strip()
            file_path = (base_path / rel_file).resolve()
            spec = json.loads(file_path.read_text(encoding="utf-8"))
            spec_base = str(file_path.parent)
        else:
            spec = json.loads(raw_body)
            spec_base = str(base_path)

        caption_html = f"\n<figcaption>{caption}</figcaption>" if caption else ""

        if is_interactive:
            frag = render_interactive_fragment(spec, fig_id=fig_id, base_dir=spec_base)
            if frag.get("model_js"):
                model_scripts.append(frag["model_js"])
            if frag.get("bindings_js"):
                bindings_scripts.append(frag["bindings_js"])

            controls_block = f"{frag['controls_html']}\n" if frag.get("controls_html") else ""
            fig_html = f'<figure id="{fig_id}">\n{controls_block}{frag["svg"]}{caption_html}\n</figure>'
        else:
            with tempfile.NamedTemporaryFile(suffix=".svg", delete=False) as tf:
                tmp_svg = tf.name
            render_from_spec(copy.deepcopy(spec), tmp_svg, base_dir=spec_base, skip_hidden=False)
            raw_svg = Path(tmp_svg).read_text(encoding="utf-8")
            try:
                Path(tmp_svg).unlink()
            except Exception:
                pass

            clean_svg = re.sub(r"^<\?xml[^>]*\?>\s*", "", raw_svg).strip()
            namespaced_svg = namespace_svg_ids(clean_svg, f"{fig_id}-")
            fig_html = f'<figure id="{fig_id}">\n{namespaced_svg}{caption_html}\n</figure>'

        placeholder = f"<!-- TECHFIG_FIGURE_{figure_counter} -->"
        figures_map[placeholder] = fig_html
        return f"\n\n{placeholder}\n\n"

    processed_body = fig_pattern.sub(replace_figure, body)

    # Convert markdown body to HTML
    body_html = _to_html(processed_body)

    # Replace placeholders with rendered figure HTML
    for placeholder, fig_html in figures_map.items():
        # Remove any surrounding <p> tags created by markdown parsers
        p_pattern = re.compile(rf"<p>\s*{re.escape(placeholder)}\s*</p>")
        if p_pattern.search(body_html):
            body_html = p_pattern.sub(fig_html, body_html)
        else:
            body_html = body_html.replace(placeholder, fig_html)

    # Header / Title construction
    title = meta.get("title", "Explainer")
    subtitle = meta.get("subtitle")
    doc_status = meta.get("status")
    style_preset = meta.get("style", "nature")

    status_badge = (
        f' <span class="tf-status tf-status-{doc_status.lower()}">{doc_status}</span>'
        if doc_status
        else ""
    )
    header_html = f'<h1 class="tf-title">{title}{status_badge}</h1>\n'
    if subtitle:
        header_html += f'<p class="tf-subtitle">{subtitle}</p>\n'

    # References section
    if all_refs:
        # Deduplicate refs by 'n'
        seen_ns = set()
        dedup_refs = []
        for r in all_refs:
            n_val = str(r.get("n", ""))
            if n_val and n_val not in seen_ns:
                seen_ns.add(n_val)
                dedup_refs.append(r)

        ref_items = []
        for r in sorted(dedup_refs, key=lambda x: int(x.get("n", 0)) if str(x.get("n", "")).isdigit() else 0):
            n = r.get("n", "")
            doi = r.get("doi")
            url = r.get("url")
            text = r.get("text")
            href = f"https://doi.org/{doi}" if (doi and not doi.startswith("http")) else (doi or url)
            if href:
                if text and text != href:
                    item_content = f'{text} &mdash; <a href="{href}">{href}</a>'
                else:
                    item_content = f'<a href="{href}">{href}</a>'
            else:
                item_content = text or ""
            ref_items.append(f'  <li id="ref-{n}">{item_content}</li>')

        references_html = (
            '<section class="tf-references">\n<h2>References</h2>\n<ol class="tf-refs">\n'
            + "\n".join(ref_items)
            + "\n</ol>\n</section>\n"
        )
    else:
        references_html = ""

    # Embedded scripts block (only if interactive figures exist)
    if bindings_scripts:
        dedup_models = []
        seen_models = set()
        for m in model_scripts:
            if m and m not in seen_models:
                seen_models.add(m)
                dedup_models.append(m)
        combined_model = ("\n".join(dedup_models) + "\n") if dedup_models else ""
        combined_bindings = "\n".join(bindings_scripts)
        script_block = (
            f"<script>\n{combined_model}{runtime_js()}\n{combined_bindings}\n</script>\n"
        )
    else:
        script_block = ""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
:root {{
{_css_vars(style_preset)}
}}
body {{
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  background: var(--tf-bg);
  color: var(--tf-fg);
  max-width: 960px;
  margin: 32px auto;
  padding: 0 20px;
  line-height: 1.6;
}}
.tf-title {{
  color: var(--tf-primary);
  margin-bottom: 0.2em;
}}
.tf-subtitle {{
  color: var(--tf-muted);
  font-size: 1.25em;
  margin-top: 0;
  margin-bottom: 1.5em;
}}
.tf-status {{
  display: inline-block;
  font-size: 0.65em;
  vertical-align: middle;
  padding: 2px 8px;
  border-radius: 4px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-left: 8px;
}}
.tf-status-established {{
  background: #e6f4ea;
  color: #137333;
  border: 1px solid #ceead6;
}}
.tf-status-active {{
  background: #e8f0fe;
  color: #1a73e8;
  border: 1px solid #d2e3fc;
}}
.tf-status-speculative {{
  background: #fef7e0;
  color: #b06000;
  border: 1px solid #feefc3;
}}
.tf-cite {{
  color: var(--tf-primary);
  text-decoration: none;
  font-weight: 600;
}}
.tf-cite:hover {{
  text-decoration: underline;
}}
.tf-references {{
  margin-top: 48px;
  border-top: 1px solid var(--tf-muted);
  padding-top: 24px;
}}
.tf-refs {{
  padding-left: 24px;
  line-height: 1.8;
}}
.tf-refs li {{
  margin-bottom: 8px;
}}
.tf-refs a {{
  color: var(--tf-primary);
  text-decoration: none;
}}
.tf-refs a:hover {{
  text-decoration: underline;
}}
.tf-controls {{
  display: flex;
  flex-wrap: wrap;
  gap: 10px 28px;
  padding: 12px 16px;
  border: 1px solid var(--tf-primary);
  border-radius: 8px;
  margin-bottom: 16px;
}}
.tf-control {{
  display: flex;
  align-items: center;
  gap: 10px;
}}
.tf-control label {{
  font-weight: 600;
  font-size: 14px;
}}
.tf-control input[type="range"] {{
  accent-color: var(--tf-primary);
  width: 150px;
}}
.tf-control select.tf-param {{
  background: var(--tf-bg);
  color: var(--tf-fg);
  border: 1px solid var(--tf-primary);
  border-radius: 4px;
  padding: 4px 8px;
  font-size: 14px;
}}
.tf-value {{
  min-width: 4.5em;
  font-variant-numeric: tabular-nums;
  font-size: 14px;
}}
figure {{
  margin: 32px 0;
}}
figure svg {{
  max-width: 100%;
  height: auto;
  display: block;
  margin: 0 auto;
}}
figcaption {{
  font-size: 0.9em;
  color: var(--tf-muted);
  text-align: center;
  margin-top: 10px;
}}
.tf-verdict-true {{ fill: var(--tf-accent, #009E73); color: var(--tf-accent, #009E73); }}
.tf-verdict-false {{ fill: var(--tf-muted, #888888); color: var(--tf-muted, #888888); }}
.tf-verdict-true .tf-readout-verdict {{ fill: var(--tf-accent, #009E73); }}
.tf-verdict-false .tf-readout-verdict {{ fill: var(--tf-muted, #888888); }}
</style>
</head>
<body>
{header_html}{body_html}
{references_html}{script_block}</body>
</html>
"""


def assemble_explainer_page(
    input_path: str | Path,
    output_path: str | Path,
) -> str:
    """Read a markdown explainer file, render it to HTML, and save to output_path.

    Args:
        input_path: Path to the input markdown file.
        output_path: Path where HTML will be written.

    Returns:
        Absolute path to the generated HTML file.
    """
    in_p = Path(input_path).resolve()
    out_p = Path(output_path).resolve()
    text = in_p.read_text(encoding="utf-8")

    html = render_explainer(text, base_dir=in_p.parent)

    out_p.parent.mkdir(parents=True, exist_ok=True)
    out_p.write_text(html, encoding="utf-8")
    return str(out_p)
