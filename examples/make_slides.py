"""Example: Generate a PowerPoint presentation with speaker notes."""
from techfig.engines.slides import create_presentation

slides = [
    {
        "title": "Research Results",
        "content": "An overview of our findings",
        "notes": "Welcome everyone to the presentation",
    },
    {
        "title": "Methodology",
        "content": "- Collected samples from 6 sites\n- Processed with standard protocol\n- Statistical analysis via ANOVA",
        "notes": "Emphasize the sample size and protocol adherence",
    },
    {
        "title": "Key Findings",
        "content": "- Treatment group showed 30% improvement\n- p < 0.01 for primary endpoint\n- No adverse effects observed",
        "notes": "This is the most important slide — pause here for questions",
    },
    {
        "title": "Conclusion",
        "content": "- Treatment is effective and safe\n- Recommend Phase 2 clinical trial\n- Funding proposal submitted",
    },
]

output = create_presentation(slides, "output/example_presentation.pptx")
print(f"Presentation saved to {output}")
