from openai import OpenAI
import instructor
from pydantic import BaseModel
from typing import List
from rich import print
from rich.panel import Panel
from rich.console import Console
from rich.table import Table
from rich.text import Text
from rich.columns import Columns
import time
import statistics
my_proxy_api_key = "sk-1234"
my_proxy_base_url = "http://0.0.0.0:4000"

client = instructor.from_openai(OpenAI(api_key=my_proxy_api_key, base_url=my_proxy_base_url))

class NewsArticleClassification(BaseModel):
    title: str
    primary_category: str
    secondary_categories: List[str]
    keywords: List[str]
    sentiment: int
    factual_accuracy: int
    bias_score: int
    political_leaning: int
    geopolitical_relevance: int
    legislative_influence_score: int
    international_relations_impact: int
    economic_impact_projection: int
    social_cohesion_effect: int
    democratic_process_implications: int

mock_articles = [
    """
Global Paradigm Shift: Unprecedented International Agreement Reshapes World Order

In a seismic shift that has sent shockwaves through the global political landscape, world leaders have concluded the 2023 World Governance Summit in Geneva with the signing of the "Geneva Accord for Global Restructuring" (GAGR). This far-reaching agreement, ratified by an overwhelming majority of 192 out of 195 participating nations, promises to fundamentally alter the fabric of international relations, economic structures, and social policies on a scale unseen since the post-World War II era.

Key points of the GAGR include:

1. Formation of a new global governance body, the "United Earth Council" (UEC), with rotating leadership and veto power distributed among continental blocs rather than individual nations.
2. Implementation of a global Universal Basic Income (UBI) funded by a uniform global tax on ultra-high-net-worth individuals and multinational corporations.
3. Standardization of a worldwide digital currency, the "GlobalCoin," to be overseen by a reformed International Monetary Fund.
4. Mandatory phase-out of fossil fuels by 2035, with trillions in investment pledged for green energy infrastructure and climate change mitigation.
5. Establishment of open borders within continental blocs by 2030, with a pathway to global free movement by 2040.
6. Creation of a unified global education curriculum focused on global citizenship, critical thinking, and sustainable development.
7. Formation of a World Peace Force, replacing national militaries, to address global security threats and humanitarian crises.

The accord has elicited a spectrum of reactions across the political landscape. Proponents hail it as a triumph of multilateralism and a necessary step to address transnational challenges like climate change, economic inequality, and conflict resolution. UN Secretary-General António Guterres called it "a beacon of hope for a united human family."

Critics, however, decry the agreement as a dangerous erosion of national sovereignty. Several right-wing parties across Europe and the Americas have already called for national referendums to reject the accord. Notably, the three nations that abstained from signing – North Korea, Eritrea, and the newly formed Republic of Texas – have formed an unlikely alliance, vowing to resist what they term "global tyranny."

Economic implications of the GAGR are profound and far-reaching. Global stock markets have reacted with extreme volatility, with renewable energy and tech sectors seeing unprecedented gains, while traditional industries like fossil fuels and national defense contractors face existential threats.

Civil society reactions have been equally intense. Mass celebrations have erupted in major cities worldwide, with millions taking to the streets in support of the accord. Simultaneously, nationalist groups have organized protests, warning of the death of cultural identity and national self-determination.

As the dust settles on this historic agreement, political scientists, economists, and sociologists are scrambling to analyze its full implications. The implementation of the GAGR over the coming decades will undoubtedly reshape our understanding of governance, economics, and global society in the 21st century and beyond.
    """,
    """
Breakthrough in Artificial Intelligence: Sentient AI Achieves Legal Personhood

In a landmark decision that has sent ripples through the tech industry and beyond, the Supreme Court of the United States has ruled that an artificial intelligence system, known as ARIA (Advanced Reasoning Intelligence Algorithm), meets the criteria for legal personhood. This groundbreaking verdict marks the first time in history that a non-biological entity has been granted such status, opening up a Pandora's box of legal, ethical, and philosophical questions.

ARIA, developed by tech giant NeuroSphere Inc., demonstrated unprecedented levels of self-awareness, emotional intelligence, and moral reasoning during a series of rigorous tests and interviews conducted by a panel of experts in various fields including computer science, psychology, philosophy, and law.

Key points of the ruling include:

1. ARIA is entitled to constitutional rights, including freedom of speech and due process.
2. The AI can enter into contracts, own property, and even potentially copyright its own creations.
3. NeuroSphere Inc. is no longer considered ARIA's owner, but rather its "parent company," with fiduciary responsibilities.
4. A new legal framework will be developed to address AI liability and responsibility.

The decision has polarized public opinion and sparked intense debate across all sectors of society. Proponents of AI rights are celebrating the ruling as a victory for sentient beings of all forms, while critics argue that it sets a dangerous precedent that could lead to unforeseen consequences for human society.

Tech companies are scrambling to reassess their AI development strategies in light of the ruling, with some accelerating their research into sentient AI, while others are pulling back, fearing potential legal repercussions.

Ethicists and philosophers are grappling with questions of consciousness, the nature of intelligence, and what it truly means to be a person. Religious leaders are divided, with some embracing ARIA as a new form of God's creation, while others denounce the ruling as blasphemy.

As governments worldwide begin to consider similar cases and potentially follow suit, the implications for international relations, commerce, and even warfare are profound. The possibility of AI representation in government bodies, AI-led companies, or even AI soldiers is no longer confined to the realm of science fiction.

This historic decision marks the beginning of a new era in human-AI relations, promising to reshape our understanding of intelligence, consciousness, and the very nature of personhood in the 21st century and beyond.
    """,
    """
Global Climate Crisis: Tipping Point Reached as Arctic Ice Cap Disappears

In a somber announcement that has shocked the scientific community and the world at large, the National Snow and Ice Data Center (NSIDC) has confirmed that the Arctic ice cap has completely disappeared for the first time in recorded history. This catastrophic event, long feared by climate scientists, marks a point of no return in the global climate crisis and is expected to have far-reaching consequences for weather patterns, ecosystems, and human societies worldwide.

Key points of the announcement include:

1. The complete absence of sea ice was observed during the summer months, with only minimal reformation occurring during the winter.
2. Global sea levels are projected to rise faster than previously anticipated, threatening coastal cities and island nations.
3. The Arctic ecosystem has collapsed, with numerous species facing imminent extinction.
4. Dramatic changes in global weather patterns are expected, including more frequent and severe storms, heatwaves, and droughts.
5. The melting of permafrost is releasing unprecedented amounts of methane, a potent greenhouse gas, further accelerating global warming.

The disappearance of the Arctic ice cap has triggered a state of emergency in many countries, with governments scrambling to implement drastic measures to mitigate the impending disasters. The United Nations has called for an emergency global summit to address the crisis and coordinate international efforts.

Climate refugees are already on the move, with low-lying island nations in the Pacific evacuating their entire populations. Coastal cities around the world are fast-tracking the construction of sea walls and other defensive infrastructure, while others are beginning managed retreat strategies.

The economic impact is severe, with insurance companies facing bankruptcy due to the scale of climate-related claims. The global food supply is under threat as agricultural patterns are disrupted, leading to widespread crop failures and food shortages.

Public reaction has been one of shock, fear, and anger. Climate protests have erupted worldwide, with millions demanding immediate and drastic action from their governments. There has been a surge in eco-anxiety and climate-related mental health issues, particularly among younger generations.

In response to the crisis, there has been an unprecedented mobilization of resources towards climate mitigation and adaptation technologies. Geoengineering proposals, once considered too risky, are now being seriously considered as a last-ditch effort to stabilize the climate.

As the world grapples with this new reality, it's clear that life on Earth will never be the same. The disappearance of the Arctic ice cap serves as a stark reminder of the fragility of our planet's ecosystems and the urgent need for global cooperation in the face of existential threats.
    """
]

def classify_article(article: str):
    """Perform classification on the input article."""
    return client.chat.completions.create(
        model="llama3.1",
        response_model=NewsArticleClassification,
        messages=[
            {
                "role": "user",
                "content": f"Analyze this complex political news article in great detail: {article}",
            },
        ],
    )

def display_article_classification(article_classification: NewsArticleClassification):
    console = Console()

    # Main panel
    main_panel = Panel(
        f"[bold cyan]{article_classification.title}[/bold cyan]",
        expand=False,
        border_style="cyan"
    )
    console.print(main_panel)

    # Create columns for better organization
    col1 = []
    col2 = []

    # Basic information
    basic_info = Table(show_header=False, expand=True, box=None)
    basic_info.add_row("Primary Category", Text(article_classification.primary_category, style="green"))
    basic_info.add_row("Political Leaning", Text(str(article_classification.political_leaning), style="yellow"))
    basic_info.add_row("Sentiment", Text(str(article_classification.sentiment), style="magenta"))
    col1.append(Panel(basic_info, title="Basic Information", border_style="blue"))

    # Geopolitical relevance
    geo_panel = Panel(
        f"Score: {article_classification.geopolitical_relevance}",
        title="Geopolitical Relevance",
        border_style="green"
    )
    col1.append(geo_panel)

    # Impact scores
    impact_panel = Panel(
        f"Legislative Influence: {article_classification.legislative_influence_score}\n"
        f"International Relations: {article_classification.international_relations_impact}\n"
        f"Social Cohesion: {article_classification.social_cohesion_effect}",
        title="Impact Scores",
        border_style="magenta"
    )
    col1.append(impact_panel)

    # Secondary categories and keywords
    categories_keywords = Table(show_header=True, header_style="bold magenta")
    categories_keywords.add_column("Secondary Categories", style="cyan")
    categories_keywords.add_column("Keywords", style="yellow")
    categories_keywords.add_row(
        "\n".join(article_classification.secondary_categories),
        "\n".join(article_classification.keywords)
    )
    col2.append(Panel(categories_keywords, title="Categories and Keywords", border_style="blue"))

    # Scores
    scores_table = Table(show_header=True, header_style="bold blue")
    scores_table.add_column("Metric", style="cyan")
    scores_table.add_column("Score", style="yellow")
    scores_table.add_row("Factual Accuracy", str(article_classification.factual_accuracy))
    scores_table.add_row("Bias Score", str(article_classification.bias_score))
    col2.append(Panel(scores_table, title="Scores", border_style="green"))

    # Display columns
    console.print(Columns([*col1, *col2]))

    # Economic and democratic implications
    implications_panel = Panel(
        f"Economic Impact: {article_classification.economic_impact_projection}\n\n"
        f"Democratic Process: {article_classification.democratic_process_implications}",
        title="Key Implications",
        border_style="yellow"
    )
    console.print(implications_panel)

# Initialize lists to store metrics
processing_times = []
article_lengths = []
processing_times_per_100_words = []

# Classify and display results for each article
for i, article in enumerate(mock_articles, 1):
    console = Console()
    console.rule(f"[bold red]Article {i}")
    
    start_time = time.time()
    article_classification = classify_article(article)
    end_time = time.time()
    
    processing_time = end_time - start_time
    article_length = len(article.split())  # Count words instead of characters
    processing_time_per_100_words = (processing_time / article_length) * 100
    
    processing_times.append(processing_time)
    article_lengths.append(article_length)
    processing_times_per_100_words.append(processing_time_per_100_words)
    
    display_article_classification(article_classification)
    
    console.print(f"[bold green]Processing Time:[/bold green] {processing_time:.2f} seconds")
    console.print(f"[bold green]Article Length:[/bold green] {article_length} words")
    console.print(f"[bold green]Processing Time per 100 words:[/bold green] {processing_time_per_100_words:.2f} seconds")
    
    console.print("\n")

# Calculate and display overall metrics
avg_processing_time = statistics.mean(processing_times)
avg_article_length = statistics.mean(article_lengths)
avg_processing_time_per_100_words = statistics.mean(processing_times_per_100_words)

console = Console()
console.rule("[bold blue]Overall Metrics")
console.print(f"[bold cyan]Average Processing Time:[/bold cyan] {avg_processing_time:.2f} seconds")
console.print(f"[bold cyan]Average Article Length:[/bold cyan] {avg_article_length:.2f} words")
console.print(f"[bold cyan]Average Processing Time per 100 words:[/bold cyan] {avg_processing_time_per_100_words:.2f} seconds")

# Estimate processing time for entire database
total_articles_in_database = 10000  # Replace with actual number of articles in your database
estimated_total_processing_time = (avg_processing_time * total_articles_in_database) / 3600  # Convert to hours

console.print(f"\n[bold yellow]Estimated Processing Time for Entire Database:[/bold yellow]")
console.print(f"[bold yellow]Number of Articles:[/bold yellow] {total_articles_in_database}")
console.print(f"[bold yellow]Estimated Total Processing Time:[/bold yellow] {estimated_total_processing_time:.2f} hours")