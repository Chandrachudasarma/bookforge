"""Asset deduplication and protected block renumbering.

When multiple articles are assembled into one book:
- Protected block IDs can collide (both start at PROTECTED_0)
- Asset filenames can collide across different articles

This module resolves both before AI processing.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from bookforge.core.models import Asset, NormalizedContent, ProtectedBlock


def renumber_protected_blocks(
    articles: list[NormalizedContent],
) -> list[NormalizedContent]:
    """Give globally unique IDs to all protected blocks across all articles.

    Must run before Assembly so that AI placeholder extraction
    and restoration work correctly on the merged body_html.
    """
    counter = 0
    result: list[NormalizedContent] = []

    for article in articles:
        renamed_blocks: list[ProtectedBlock] = []
        html = article.body_html

        for block in article.protected_blocks:
            old_id = block.block_id
            new_id = f"PROTECTED_{counter}"
            counter += 1

            # Replace in HTML (both in data-block-id attributes and placeholders)
            html = html.replace(f'data-block-id="{old_id}"', f'data-block-id="{new_id}"')
            html = html.replace(f"<<<{old_id}>>>", f"<<<{new_id}>>>")

            renamed_blocks.append(replace(block, block_id=new_id))

        result.append(
            replace(article, body_html=html, protected_blocks=renamed_blocks)
        )

    return result


def deduplicate_assets(
    articles: list[NormalizedContent],
) -> tuple[list[Asset], dict[str, str]]:
    """Merge assets from all articles, resolving filename conflicts.

    Returns:
        (deduplicated_assets, rename_map)
        rename_map: {old_filename: new_filename} for any renamed assets
    """
    seen: dict[str, Asset] = {}  # filename → Asset
    rename_map: dict[str, str] = {}

    for article in articles:
        for asset in article.assets:
            if asset.filename not in seen:
                seen[asset.filename] = asset
            else:
                # Same filename but different file — rename with suffix
                existing = seen[asset.filename]
                if existing.file_path != asset.file_path:
                    stem = Path(asset.filename).stem
                    suffix = Path(asset.filename).suffix
                    count = sum(1 for k in seen if k.startswith(stem))
                    new_name = f"{stem}_{count}{suffix}"
                    rename_map[asset.filename] = new_name
                    renamed = replace(asset, filename=new_name)
                    seen[new_name] = renamed

    return list(seen.values()), rename_map
