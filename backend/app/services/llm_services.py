from openai import AsyncOpenAI

from app.enums.core import EntityType
from app.schemas.llm import DomainClassificationResult, EntryParseResult
from app.services.llm_platform import extract_structured


async def parse_entry(
    url: str,
    html: str,
    client: AsyncOpenAI | None = None,
    description: str | None = None,
) -> EntryParseResult:
    """
    Parse a webpage entry into structured data.

    Args:
        url: The URL of the webpage
        html: The text content extracted from HTML (not raw HTML)
        client: Optional OpenAI client
        description: Optional description of the person who owns the blog

    Returns:
        EntryParseResult with extracted information
    """
    system_prompt = """
Your job is to complete a unit of work in a larger goal. The larger goal is, given the webpage of a
writer's personal blog, to index all the entries of the blog. The steps are as follows:
1. Run BFS to collect all unique URLs that share the same domain as the starting URL
2. For each URL, crawl the webpage and parse the entry into structured data


The unit of work you will be doing is to parse the text content obtained by crawling a single URL into structured data.

An entry should be a self-contained written piece that represents personal expression, reflection, or narrative. Valid entries include:
- Personal takes and opinions (on any topic)
- Essays (analytical, argumentative, reflective, or narrative)
- Personal experiences and stories
- Advice columns or guidance pieces
- Creative non-fiction (memoirs, personal narratives, literary journalism)

Since this is the web, there will be a lot of noise. You should not pursue entries that are primarily:
- Standalone quotes or quote collections (even if long, substantial, or attributed) - these are NOT entries regardless of length
- Art galleries, portfolios, or visual art showcases (unless accompanied by substantial written narrative)
- Pure image or video content without substantial written narrative
- Product listings, catalogs, or commercial pages
- Simple status updates or micro-posts without substantive content

If the text content is not representative of a valid entry, you should NOT pursue, and can leave
all other fields blank.

The summary should be a concise summary of the entry that captures the main idea or message written from the third person.
"""

    user_prompt = f"""
URL:
{url}

Text content:
{html}
"""

    if description:
        user_prompt += f"""
Description of the writer:
{description}
"""

    user_prompt += """
You've been provided the URL and text content for a web page. Parse the text content into structured data.
        """

    return await extract_structured(
        prompt=user_prompt,
        output_model=EntryParseResult,
        system_prompt=system_prompt,
        client=client,
    )


async def classify_domain(
    url: str, html: str, client: AsyncOpenAI | None = None
) -> DomainClassificationResult:
    """
    Classify a domain based on its webpage content.

    Args:
        url: The URL of the webpage
        html: The text content extracted from HTML (not raw HTML)

    Returns:
        DomainClassificationResult with extracted information
    """

    entity_types = ", ".join([e.value for e in EntityType])

    system_prompt = f"""
You're given the URL and text content of a webpage. Your task is to extract information about the webpage.

Since this is the web, there will be a lot of noise. Furthermore, you will only be provided with the domain's home page text content, so you won't have much to go on. 

In the most common case of personal blogs, the home page (e.g. the page for which you will be provided the text) may already have a list of entries, essays, notes, posts, etc.

However, in other cases, the home page may not. In these cases, you should determine if the website is a personal blog by checking if there is a way for a user to navigate to the blog's entries, notes, posts, essays, etc. If there is not a direct way for the user to navigate to the blog's writing content, then the website is likely not a personal blog.

The cost of getting this wrong is pretty low, so use your best judgement.

You will be provided the URL and text content for a web page. Determine the following:
- url: The URL
- entity: The type of the entity represented by the website. Must be one of: {entity_types}. If not readily obvious, it is likely "person". If no entity type can be determined, output UNKNOWN.
- name: The name of the entity that is writing. If none is present, output "NONE"
- blog: Whether or not the website is a blog
"""

    prompt = f"""
URL:
{url}

Text content: 
{html}

Your task is to determine if the website should be indexed as a personal blog.
        """

    return await extract_structured(
        system_prompt=system_prompt,
        model_name="gpt-5-mini-2025-08-07",
        prompt=prompt,
        output_model=DomainClassificationResult,
        client=client,
    )
