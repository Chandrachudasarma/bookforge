"""Generate 3 sample completed jobs for demo purposes.

Run once to populate data/jobs/ with real EPUB output:
  python scripts/generate_samples.py

No AI calls — uses rewrite_percent=0 and generators off.
"""

import asyncio
import json
import shutil
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

# Ensure we can import bookforge
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from bookforge.core.config import Config
from bookforge.core.models import BookMetadata, JobConfig
from bookforge.core.pipeline import Pipeline
from bookforge.jobs.models import FileResult, Job, JobProgress, JobStatus
from bookforge.jobs.store import FileJobStore


SAMPLES = [
    {
        "job_id": "sample_001_intro",
        "title": "Introduction to Scientific Computing",
        "author": "Jane Smith",
        "files": {
            "introduction.html": """<!DOCTYPE html>
<html><body>
<h1>Introduction to Scientific Computing</h1>
<p>Scientific computing has become an indispensable tool across virtually every discipline of modern research. From climate modeling to drug discovery, computational methods enable researchers to simulate complex systems, analyze massive datasets, and test hypotheses that would be impossible to explore through experimentation alone.</p>
<h2>Historical Context</h2>
<p>The origins of scientific computing trace back to the early days of electronic computers in the 1940s and 1950s. John von Neumann's pioneering work on numerical weather prediction demonstrated that computers could tackle problems of genuine scientific importance.</p>
<h2>Modern Applications</h2>
<p>Today, scientific computing encompasses a vast range of methodologies including finite element analysis, Monte Carlo simulation, molecular dynamics, and machine learning. These tools have transformed fields as diverse as astrophysics, genomics, materials science, and economics.</p>
<p>The increasing availability of high-performance computing resources, combined with advances in algorithms and software, has democratized access to computational methods. Researchers who previously relied on analytical approaches now routinely employ numerical simulations as a core part of their methodology.</p>
</body></html>""",
        },
    },
    {
        "job_id": "sample_002_table",
        "title": "Quarterly Research Output Analysis",
        "author": "John Doe",
        "files": {
            "research_analysis.html": """<!DOCTYPE html>
<html><body>
<h1>Quarterly Research Output Analysis</h1>
<p>This report presents a comprehensive analysis of research output metrics for the academic year 2025-2026. The data encompasses publications, citations, and funding across all departments.</p>
<h2>Publication Metrics</h2>
<table>
<thead><tr><th>Department</th><th>Papers Published</th><th>Citations</th><th>Impact Factor</th><th>Funding ($M)</th></tr></thead>
<tbody>
<tr><td>Computer Science</td><td>142</td><td>3,847</td><td>4.2</td><td>12.5</td></tr>
<tr><td>Physics</td><td>98</td><td>5,231</td><td>6.1</td><td>18.3</td></tr>
<tr><td>Biology</td><td>156</td><td>4,102</td><td>5.3</td><td>22.7</td></tr>
<tr><td>Chemistry</td><td>87</td><td>2,946</td><td>4.8</td><td>9.1</td></tr>
<tr><td>Mathematics</td><td>63</td><td>1,204</td><td>3.1</td><td>4.2</td></tr>
</tbody>
</table>
<h2>Key Findings</h2>
<p>Biology leads in total publications with 156 papers, while Physics achieves the highest average impact factor at 6.1. Computer Science shows strong growth with a 23% increase over the previous year.</p>
<p>Cross-departmental collaborations account for 34% of all publications, up from 28% in the prior year, reflecting the university's strategic emphasis on interdisciplinary research.</p>
</body></html>""",
        },
    },
    {
        "job_id": "sample_003_multi",
        "title": "Advances in Renewable Energy: A Multi-Author Volume",
        "author": "Multiple Authors",
        "files": {
            "chapter1_solar.html": """<!DOCTYPE html>
<html><body>
<h1>Solar Energy: Current State and Future Prospects</h1>
<p>Solar photovoltaic technology has experienced remarkable cost reductions over the past decade, with module prices declining by approximately 90% since 2010. This chapter examines the technological innovations driving this transformation and projects future developments in solar energy conversion efficiency.</p>
<p>Perovskite solar cells represent the most promising emerging technology, with laboratory efficiencies exceeding 25% and the potential for low-cost manufacturing through solution processing techniques.</p>
</body></html>""",
            "chapter2_wind.html": """<!DOCTYPE html>
<html><body>
<h1>Wind Energy: Offshore Developments and Grid Integration</h1>
<p>Offshore wind energy has emerged as a cornerstone of the global energy transition. Floating wind turbine platforms now enable deployment in deep-water locations previously considered inaccessible, vastly expanding the potential resource base.</p>
<p>Grid integration remains a critical challenge. Variable renewable energy sources require sophisticated forecasting systems, flexible generation assets, and expanded transmission infrastructure to maintain system reliability.</p>
</body></html>""",
        },
    },
]


async def generate_sample(pipeline, sample, store):
    job_id = sample["job_id"]
    print(f"  Generating: {sample['title']}")

    # Create job directory and input files
    job_dir = store.get_job_dir(job_id)
    input_dir = job_dir / "input"
    input_dir.mkdir(parents=True, exist_ok=True)
    (job_dir / "output").mkdir(exist_ok=True)

    input_paths = []
    for fname, content in sample["files"].items():
        fpath = input_dir / fname
        fpath.write_text(content)
        input_paths.append(fpath)

    metadata = BookMetadata(
        title=sample["title"],
        authors=[sample["author"]],
        publisher_name="BookForge Demo",
        year=2026,
    )
    job_config = JobConfig(
        output_formats=["epub"],
        generate_title=False,
        generate_preface=False,
        generate_acknowledgement=False,
        rewrite_percent=0,
    )

    # Run pipeline
    normalized = []
    for fpath in input_paths:
        nc = await pipeline.process_file(fpath, job_config)
        normalized.append(nc)
    outputs = await pipeline.process_book(normalized, metadata, job_config)

    # Copy outputs
    final_paths = []
    for p in outputs:
        dest = job_dir / "output" / p.name
        shutil.copy2(p, dest)
        final_paths.append(str(dest))

    # Write job.json
    job = Job(
        job_id=job_id,
        status=JobStatus.COMPLETED,
        input_files=[str(p) for p in input_paths],
        metadata=asdict(metadata),
        config=asdict(job_config),
        progress=JobProgress(
            total_files=len(input_paths),
            completed_files=len(input_paths),
            succeeded=len(input_paths),
            current_stage="completed",
        ),
        created_at=datetime.now(timezone.utc).isoformat(),
        output_dir=str(job_dir / "output"),
    )
    store.write_job(job)

    # Write status and results
    store.write_status(job_id, job.progress)
    store.write_file_result(job_id, FileResult(
        file_path="book",
        status="success",
        output_paths=final_paths,
    ))

    print(f"    Done: {len(outputs)} output(s), {sum(p.stat().st_size for p in outputs):,} bytes")


async def main():
    config = Config.load()
    pipeline = Pipeline(config.as_dict())
    store = FileJobStore(Path(config.get("worker.state_dir", "data/jobs")).resolve())

    print("Generating sample jobs...")
    for sample in SAMPLES:
        await generate_sample(pipeline, sample, store)

    print(f"\nDone. {len(SAMPLES)} sample jobs created in {store.base_dir}")


if __name__ == "__main__":
    asyncio.run(main())
