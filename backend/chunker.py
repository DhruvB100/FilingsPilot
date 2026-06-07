"""
Turns the downloaded html filings into chunks with metadata (company, year, section, page).
Run: python -m backend.chunker
"""
import os
import re
import json
import glob
import warnings
from bs4 import BeautifulSoup, NavigableString, XMLParsedAsHTMLWarning

from backend import config

# inline xbrl files are technically xhtml, html parser handles them fine
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

PAGE_MARK = "@@PAGE@@"
HEAD_MARK = "@@H@@"
CHUNK_SIZE = 2000  # chars, roughly 500 tokens
MIN_CHUNK = 150

HIDDEN = re.compile(r"display:\s*none", re.I)
BOLD = re.compile(r"font-weight:\s*(bold|700)", re.I)
PAGE_BREAK = re.compile(r"page-break-(before|after)\s*:\s*always", re.I)


def clean_html(path):
    with open(path, "rb") as f:
        soup = BeautifulSoup(f, "lxml")

    # hidden stuff = the inline XBRL header and empty spacer cells
    for tag in soup.find_all(style=HIDDEN):
        tag.decompose()
    for tag in soup(["script", "style", "head", "title"]):
        tag.decompose()

    # tables: one line per row with | between cells, otherwise numbers get scattered everywhere
    for tr in soup.find_all("tr"):
        cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
        cells = [c for c in cells if c and c not in ("$", "%", ")")]
        tr.replace_with(NavigableString("\n" + " | ".join(cells) + "\n"))

    # headings: a bold piece of text that is the whole line
    for tag in soup.find_all(style=BOLD):
        text = tag.get_text(" ", strip=True)
        parent = tag.find_parent(["div", "p"])
        if not parent or parent.get_text(" ", strip=True) != text:
            continue
        if 3 <= len(text) <= 100 and len(re.findall(r"[A-Za-z]", text)) >= 3 and not text.endswith("."):
            tag.insert(0, NavigableString(HEAD_MARK))

    for tag in soup.find_all(style=PAGE_BREAK):
        if "before" in tag["style"].lower():
            tag.insert_before(NavigableString(PAGE_MARK))
        else:
            tag.insert_after(NavigableString(PAGE_MARK))

    # block elements end with a newline so words from different paragraphs don't glue together
    # BUT TD's filings use <div style="display:inline-block">&nbsp;</div> as the space between
    # every single word, so those divs must not get a newline (was getting one word per line)
    for tag in soup.find_all(["p", "div", "li", "h1", "h2", "h3", "h4", "br"]):
        if "inline" in tag.get("style", "").replace(" ", "").lower():
            continue
        tag.append(NavigableString("\n"))

    return soup.get_text("")


DOC_TYPES = {
    "form 10-k": "10-K",
    "form 40-f": "40-F",
    "annual information form": "Annual Information Form",
    "management's discussion": "MD&A",
    "annual report": "Annual Report",
    "financial statements": "Financial Statements",
}


def guess_doc_type(text):
    # whichever title shows up first on the cover wins
    # (the MD&A mentions the AIF on page 1 too so just checking "in" was wrong)
    start = text[:4000].lower().replace("’", "'")
    best, best_pos = "Other", len(start)
    for key, name in DOC_TYPES.items():
        pos = start.find(key)
        if pos != -1 and pos < best_pos:
            best, best_pos = name, pos
    return best


def is_caps_heading(line):
    letters = re.findall(r"[A-Za-z]", line)
    return 4 <= len(line) <= 80 and len(letters) >= 4 and line.upper() == line and "|" not in line


def split_page(lines, section):
    """returns list of (section, text) chunks for one page, and the last section seen"""
    chunks = []
    current = []
    size = 0
    for line in lines:
        if line.startswith(HEAD_MARK):
            heading = line.replace(HEAD_MARK, "").strip()
            # new section starts, flush what we have
            if size >= MIN_CHUNK:
                chunks.append((section, "\n".join(current)))
                current, size = [], 0
            section = heading
            current.append(heading)
            continue
        if size + len(line) > CHUNK_SIZE and size >= MIN_CHUNK:
            chunks.append((section, "\n".join(current)))
            current, size = [], 0
        current.append(line)
        size += len(line)
    if size >= MIN_CHUNK:
        chunks.append((section, "\n".join(current)))
    elif chunks and current:
        # leftover tiny bit, glue onto previous chunk
        sec, txt = chunks[-1]
        chunks[-1] = (sec, txt + "\n" + "\n".join(current))
    return chunks, section


def chunk_document(path, meta, doc):
    text = clean_html(path)
    doc_type = guess_doc_type(text)
    pages = text.split(PAGE_MARK)

    results = []
    section = doc_type
    for page_num, page in enumerate(pages, start=1):
        lines = [re.sub(r"[ \t\xa0]+", " ", l).strip() for l in page.split("\n")]
        lines = [l for l in lines if l and l != HEAD_MARK]
        lines = [HEAD_MARK + l if is_caps_heading(l) else l for l in lines]
        page_chunks, section = split_page(lines, section)
        for sec, content in page_chunks:
            results.append({
                "ticker": meta["ticker"],
                "company": meta["company"],
                "fiscal_year": meta["fiscal_year"],
                "form": meta["form"],
                "doc_type": doc_type,
                "doc_file": doc["file"],
                "doc_url": doc["url"],
                "page": page_num,
                "section": sec[:200],
                "content": content,
            })
    return results


def run():
    out_dir = os.path.join(config.DATA_DIR, "chunks")
    os.makedirs(out_dir, exist_ok=True)
    for meta_path in sorted(glob.glob(os.path.join(config.RAW_DIR, "*", "*", "meta.json"))):
        with open(meta_path) as f:
            meta = json.load(f)
        out_path = os.path.join(out_dir, f"{meta['ticker']}_{meta['fiscal_year']}.jsonl")
        if os.path.exists(out_path):
            continue
        all_chunks = []
        for doc in meta["docs"]:
            path = os.path.join(os.path.dirname(meta_path), doc["file"])
            all_chunks += chunk_document(path, meta, doc)
        with open(out_path, "w", encoding="utf-8") as f:
            for c in all_chunks:
                f.write(json.dumps(c) + "\n")
        chars = sum(len(c["content"]) for c in all_chunks)
        print(f"{meta['ticker']} {meta['fiscal_year']}: {len(all_chunks)} chunks, {chars:,} chars")


if __name__ == "__main__":
    run()
