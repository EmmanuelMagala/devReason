# DevReason manual diagrams

The [manual](../../DEVREASON_MANUAL.md) contains the Mermaid source for each
diagram. The local generated HTML manual embeds the SVG images.
It does not require a remote diagram library to display them.

| File | Diagram |
| --- | --- |
| [diagram-1.svg](diagram-1.svg) | Active system architecture. |
| [diagram-2.svg](diagram-2.svg) | GitHub authorization and verified repository import. |
| [diagram-3.svg](diagram-3.svg) | Main database record relationships. |
| [diagram-4.svg](diagram-4.svg) | Review submission, worker execution, streaming, and saved recovery. |
| [diagram-5.svg](diagram-5.svg) | LangGraph nodes and conditional routes. |

## Document checks

Document generation used the code and implementation evidence available on
13 October 2026. The document checks found:

- Five diagrams rendered without errors.
- No missing file among 250 local links in the manual.
- All 38 documented API route claims matched route source.
- All 15 registered graph nodes had descriptions.
- No broken HTML section links or desktop/mobile page overflow.
- No empty page in the 42-page PDF.

All PDF pages were rendered for layout inspection. The graph and sequence
diagram pages were also inspected at a larger scale. Local check evidence is
under `.audit/manual-render/`; that folder is excluded from version control.

The manual cites the recorded 79-test backend gate and 12-test browser gate.
Document creation did not perform a new application regression run or live
analysis. The manual separates source behavior, fixture checks, live evidence,
and unverified release behavior.
