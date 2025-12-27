from services.llm_platform import extract_structured
from schemas.llm import DomainClassificationResult, EntryParseResult


async def parse_entry(url: str, html: str) -> EntryParseResult:
    """
    Parse a webpage entry into structured data.

    Args:
        url: The URL of the webpage
        html: The cleaned HTML content

    Returns:
        EntryParseResult with extracted information
    """
    prompt = f"""
        You're given the HTML of a webpage. Your task is to parse the unstructured contents of the web page into a structured
        form to provide content to an RSS reader.

        URL:
        {url}
        
        HTML: 
        {html}

        An entry should be a self-contained written piece that represents personal expression, reflection, or narrative. Valid entries include:
        - Personal takes and opinions (on any topic)
        - Essays (analytical, argumentative, reflective, or narrative)
        - Personal experiences and stories
        - Advice columns or guidance pieces
        - Creative non-fiction (memoirs, personal narratives, literary journalism)
        
        DO NOT pursue entries that are primarily:
        - Standalone quotes or quote collections (even if long, substantial, or attributed) - these are NOT entries regardless of length
        - Media pages, quote pages, or pages displaying someone else's words (look for indicators like "Back to Media", attribution at the end like "- Author Name", or navigation suggesting it's a quote/media section)
        - Pages that are primarily reproducing or displaying content from another source (interviews, transcripts, quotes) without substantial original commentary
        - Art galleries, portfolios, or visual art showcases (unless accompanied by substantial written narrative)
        - Pure image or video content without substantial written narrative
        - Product listings, catalogs, or commercial pages
        - Simple status updates or micro-posts without substantive content
        
        CRITICAL: A quote is NOT an entry, even if it's long or substantial. If the page is primarily displaying a quote (with attribution like "- Author Name" at the end, or navigation like "Back to Media"), it is NOT a valid entry.
        
        Edge cases to consider:
        - An essay that USES quotes as supporting evidence WITH substantial original commentary, analysis, or personal reflection = VALID entry
        - A quote page/media page displaying someone else's words (even if long) = NOT a valid entry
        - An art portfolio WITH detailed artist statements or narrative descriptions = VALID entry
        - A photo essay WITH substantial written narrative = VALID entry
        - A quote collection page WITHOUT commentary = NOT a valid entry
        - An art gallery WITH only titles and dates = NOT a valid entry
        - A page with "Back to Media" or similar navigation indicating it's a media/quote section = NOT a valid entry
        
        You've been provided the HTML for a web page with content. Determine the following:
        - should_pursue: 
            - Is the HTML representative of a standalone entry (as defined above), written in English? If no, we should not pursue.
            - Is this a quote page, media page, or page primarily displaying someone else's words? Look for indicators like "Back to Media" navigation, attribution at the end (e.g., "- Author Name"), or other signals that this is a quote/media section. If yes, do NOT pursue - quotes are NOT entries regardless of length.
            - Is the content primarily reproducing or displaying content from another source (quotes, interviews, transcripts) without substantial original written commentary by the page author? If yes, do NOT pursue.
            - Does the content have substantial original written narrative by the author (not just quotes, images, or minimal text)? If no, we should not pursue.
            - If the HTML is only representative of a part of an entry (e.g. a teaser, excerpt, or tag page), then it is likely that the full entry is located at a separate URL on the website. In this case, we should not pursue the partial content.
            - Similarly, if the HTML is representative of multiple entries (e.g. a compilation, feed, or index page), it is likely the individual entries are located at separate URLs, and you should not attempt to pursue the collection as one.
            - If the HTML is representative of a text editor for comments or edits, do not pursue.
            - If the HTML is primarily a quote, image gallery, or art showcase without substantial written narrative, do not pursue.

        You only need to fill the remainder of the fields if you should_pursue is True. Otherwise, you may leave them all blank, e.g. "" for a string value and [] for a list value.

        If the HTML is not representative of a valid entry, fill in the remaining fields with empty strings. Otherwise, proceed:
        - title: What is the title?
        - summary: Summarize the above content in two sentences. Be creative and try to capture the essence of the text. Does not have to be an objective summary, try to mimick the voice of the author as much as you can. Do not use `the author` or `I` as pronouns. Instead, speak directly to the reader.
        - topics: What are some key relevant topics? Output a list of strings.
        - author: Who wrote the article? If multiple people contributed to it, include all of their names. If it's unclear, you should put "Unknown".
        - date_published: When was the article published? If unknown or invalid, you should put "Unknown". Make sure that if you output a date, that it is in the format "YYYY-MM-DD".

        In any part of your response, replace null bytes with spaces. You are not allowed to include null bytes in your response.
        """

    return await extract_structured(prompt, EntryParseResult)


async def classify_domain(url: str, html: str) -> DomainClassificationResult:
    """
    Classify a domain based on its webpage content.

    Args:
        url: The URL of the webpage
        html: The cleaned HTML content

    Returns:
        DomainClassificationResult with extracted information
    """
    prompt = f"""
        You're given the URL and HTML of a webpage. Your task is extract information about the webpage

        URL:
        {url}
        
        HTML: 
        {html}
        
        You've been provided the URL and HTML for a web page with content. Determine the following:
        - url: The URL
        - entity: The type of the entity represented by the website; if not readily obvious, it is likely an individual
        - name: The name of the entity that is writing. If none is present, output "NONE"
        - blog: Whether or not the website is a blog
        """

    return await extract_structured(prompt, DomainClassificationResult)
