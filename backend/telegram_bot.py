"""
Kokoro Studio Auto-Pilot
=========================
Runs daily: Starts at 7 AM, generates stories, uploads to YouTube.
Handles upload limits automatically. Telegram is the monitor.

Start: python telegram_bot.py
Stop:  /stop  (in Telegram)
Start: /start (in Telegram)
Status: /status
"""

import os
import sys
import asyncio
import random
import logging
import json
import aiohttp
import tempfile
from datetime import datetime, time
from telegram import Update
from telegram.error import NetworkError, TimedOut
from telegram.request import HTTPXRequest
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)

# Load backend/.env so secrets live in one place instead of this script tree.
try:
    from dotenv import load_dotenv

    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
except Exception:  # pragma: no cover - dotenv is optional
    pass

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
VOICE_MALE = "am_liam"
VOICE_FEMALE = "af_heart"
SPEED = 1.08
NICHE = "psychology"
PROJECT_ID = "5bc38401-ab6b-414b-848a-cd219047e05b"
AUTOPILOT_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()
AUTHORIZED_CHAT_ID = AUTOPILOT_CHAT_ID
DEFAULT_VIDEO_FOLDERS = [
    f.strip()
    for f in os.getenv(
        "DEFAULT_VIDEO_FOLDERS",
        "odlysatisfy,sandsatisfy,sandsound,SandTagious,stablesatisfaction",
    ).split(",")
    if f.strip()
] or None

# Max retry attempts for selecting an unused theme
MAX_THEME_RETRIES = 10


def detect_lead_gender(script: str, theme: str = "") -> str:
    """
    Detect the lead character's gender from the script text and theme.
    Returns "male" or "female" based on pronouns and gendered terms.
    """
    # Combine script and theme for analysis
    text = (script + " " + theme).lower()

    # Male indicators (when the lead is male, he refers to female partners)
    male_indicators = [
        "my wife",
        "my girlfriend",
        "my fiancee",
        "my fiance",
        "my sister",
        "my mother",
        "my mom",
        "my daughter",
        "she told me",
        "she said",
        "she was",
        "she had",
        "her phone",
        "her messages",
        "her secret",
        "my woman",
        "my lady",
    ]

    # Female indicators (when the lead is female, she refers to male partners)
    female_indicators = [
        "my husband",
        "my boyfriend",
        "my fiance",
        "my brother",
        "my father",
        "my dad",
        "my son",
        "he told me",
        "he said",
        "he was",
        "he had",
        "his phone",
        "his messages",
        "his secret",
        "my man",
        "my guy",
    ]

    # Count matches
    male_score = sum(1 for indicator in male_indicators if indicator in text)
    female_score = sum(1 for indicator in female_indicators if indicator in text)

    # Also check for first-person gendered references
    # If the script mentions "as a man" or "as a woman"
    if "as a man" in text or "as a guy" in text or "as a husband" in text:
        male_score += 3
    if "as a woman" in text or "as a wife" in text or "as a girlfriend" in text:
        female_score += 3

    # Check for father/mother references about the lead
    if "i was a single father" in text or "i was a dad" in text:
        male_score += 5
    if "i was a single mother" in text or "i was a mom" in text:
        female_score += 5

    # Determine gender based on score
    if female_score > male_score:
        return "female"
    elif male_score > female_score:
        return "male"
    else:
        # Default to male if unclear (matching original behavior)
        return "male"


PROMPTS = [
    # BETRAYAL + REVENGE (highest viral potential)
    "my wife asked for a divorce after I refused to let her sister move in",
    "my best friend accused me of ruining his wedding",
    "my girlfriend had been living a double life and I had proof",
    "my partner proposed but I found out they were already married",
    "my best friend and I fell for the same person and it destroyed our friendship",
    "my wife left me because of something my mother told her",
    "my ex came back with a secret that changed everything",
    "my wife had a secret bank account and I found out what it was for",
    "my boyfriend was catfishing multiple women including my best friend",
    "my partner was gaslighting me and I did not realize until it was too late",
    "my partner was planning to leave me and I found the hidden suitcase",
    "I found out my wife was cheating with my therapist",
    "my wife had been meeting my best friend behind my back for months",
    "I discovered my fiance was still legally married to someone else",
    "my girlfriend faked her pregnancy to keep me from leaving",
    "my wife was secretly texting my brother every night",
    "I found out my boyfriend was actually two different people",
    "my partner was using our savings to fund their gambling addiction",
    "my wife was secretly recording our private conversations",
    "I found out my entire family has been lying to me for 20 years",
    "my father left when I was 5 and just showed up at my doorstep with a confession",
    "my mother had been hiding a second family from us for decades",
    "I found a hidden room in my house that contained my parents darkest secret",
    "my father was living a double life and I accidentally discovered his second family",
    "I was adopted and just found my biological family but they did not want me",
    "my sister was the anonymous donor who saved my life but she never told me",
    "I found out my brother was not biologically related to our family",
    "my mother had been forging my fathers signature for 15 years",
    "my grandmother left a will that revealed a shocking family secret",
    "my uncle had been impersonating my dead father for years",
    "I discovered my parents were actually cousins",
    "my family was hiding a crime that happened before I was born",
    "I found letters proving my grandfather was a completely different person",
    "my boss fired me but I was the only one who knew the company was about to collapse",
    "I found out my company was using my ideas and giving credit to someone else",
    "my coworker took credit for my work and got promoted over me",
    "I discovered my boss was running a pyramid scheme under the company name",
    "I found out my promotion was given to someone who bribed the CEO",
    "my coworker was secretly recording all our meetings",
    "I discovered my company was mining my personal data and selling it",
    "I found out my charity was a front and I was laundering money without knowing",
    "my employer was paying me half of what they promised and I had proof",
    "my business partner was stealing from our company for three years",
    "I discovered my coworker was sending company secrets to our competitor",
    "my boss was taking credit for my inventions and patenting them under his name",
    "I found out my salary was being split between two fake employees",
    "I discovered my boss had been forging my signatures on legal documents",
    "I was blamed for a crime I did not commit but the real culprit was someone I loved",
    "I discovered my dream job was a front for something much darker",
    "I found out my college roommate was a spy",
    "my neighbor was secretly filming me and I found the cameras",
    "my brother was the one who had been hacking into my accounts",
    "I discovered my flight had been deliberately delayed and the reason was terrifying",
    "I found out my teacher was the one who had been sabotaging my grades",
    "my best friend was the one who reported me to the police",
    "my best friend was the one who leaked my private photos",
    "I discovered my medicine was placebo and I had been getting better on my own",
    "I found out my scholarship was given to someone who bought their way in",
    "I discovered my inheritance was stolen by my own lawyer",
    "my neighbor was running an illegal operation from their basement",
    "I discovered the hotel I was staying in had hidden cameras everywhere",
    "I found a body in the storage unit I just rented",
    "my rideshare driver was not who they claimed to be",
    "I discovered my online therapist was completely fake",
    "I found out my gym trainer had a criminal record I should have known about",
    "I discovered my real estate agent was deliberately hiding property defects",
    "my childhood best friend disappeared and just reappeared with no memory of me",
    "I found a letter from my late grandmother that revealed a shocking secret",
    "I discovered my online friend was actually someone I knew in real life",
    "I discovered my dream house was built on a cemetery",
    "my tattoo artist was using the same needle on everyone",
    "I found out my wife was the anonymous caller who reported me",
    "I discovered my best friend had been impersonating me online for years",
    "my neighbor turned out to be someone I had been searching for my whole life",
    "I caught my roommate stealing but the reason broke my heart",
    "I discovered my coach had been manipulating all the athletes",
    "my babysitter was not who she said she was",
    "I found out my landlord had been entering my apartment when I was away",
    "I discovered my identity had been stolen by someone in my own family",
    "my car mechanic had been deliberately sabotaging my car for repeat business",
    "I found out my dentist had been performing unnecessary procedures",
    "I discovered a hidden talent that changed my entire career",
    "I found a strangers diary and it turned out to be about me",
    "my shy coworker turned out to be a famous anonymous blogger",
    "I discovered my quiet neighbor was a retired secret agent",
    "I found out my mailman had been writing personalized poems for every house",
    "my dog led me to an abandoned puppy that became my best friend",
    "I discovered the homeless man outside my office was actually a millionaire",
    "I found out my Uber driver was a retired NASA scientist",
    "my librarian turned out to be a bestselling author under a pen name",
    "I discovered my barber was moonlighting as a stand-up comedian",
    "I woke up in a hospital and nobody could explain how I got there",
    "I found footprints leading to my bed but none leading away",
    "my reflection in the mirror moved a split second after I did",
    "I heard knocking from inside my walls every night at 3am",
    "my new house came with a locked room I was told never to open",
    "I found old photographs in my attic of people who looked exactly like me",
    "my sleep tracker recorded me walking for 2 hours but I was in bed",
    "I discovered my smart home was being controlled by someone else",
    "I found a hidden camera in my vacation rental bathroom",
    "my dreams started predicting real events the next day",
    "I was falsely accused of stealing at work but the real thief was my manager",
    "I discovered my doctor had been misdiagnosing patients for insurance money",
    "I found out my landlord was charging me double the rent and pocketing the difference",
    "I was in a car accident and discovered the other driver was my long lost brother",
    "I found a notebook that predicted everything that would happen in my town",
    "my childhood home was being demolished and I found a time capsule I buried",
    "I discovered my college professor was secretly a world famous hacker",
    "I found out the random stranger who saved my life was my biological father",
    "my coworker was secretly feeding information to our biggest competitor",
    "I found out my dentist had been selling patient records to insurance companies",
    "my neighbor was secretly running a shelter for abandoned animals in their garage",
    "I discovered the viral video everyone was sharing was filmed in my own house",
    "I found out my childhood home was worth 10 million but my parents never told me",
    "I discovered my lifelong allergy was actually caused by something in my own walls",
    "I found out my best friend had been secretly paying for my mothers medication",
    "my Uber driver turned out to be the CEO of a billion dollar company",
    "I discovered the fortune teller I visited actually knew things she should not know",
    "I found out my gym buddy was a professional bodyguard working undercover",
    "I discovered my cat had been leading me to hidden treasures around the neighborhood",
    "I found out my childhood bully had become my boss and recognized me on day one",
    "my wife surprised me with a DNA test that revealed something shocking about my family",
    "I discovered my coworker was secretly the anonymous donor who funded my education",
    "I found out my sister had been writing anonymous love letters to my husband",
    "my parents had been secretly funding my rivals business for 10 years",
    "I discovered my gym locker neighbor was a professional thief targeting our gym members",
    "I found out my favorite barista was actually a neuroscientist studying customer behavior",
    "my childhood imaginary friend turned out to be based on a real person who lived next door",
    "I discovered my driving instructor had been secretly recording every lesson for a documentary",
    "I found out my wife was secretly competing against me in an online competition",
    "my handyman was secretly building a hidden underground room beneath my house",
    "I discovered my neighbor was a retired judge and had been solving cold cases from home",
    "I found out my pet sitter was throwing secret parties at my house while I was away",
    "my seemingly perfect marriage was built on a lie that took 12 years to uncover",
    "I discovered my company wellness program was actually an experiment on employees",
    "I found out my mailman had been intercepting my letters for a decade",
    "my yoga instructor was secretly filming classes and selling them online",
    "I discovered my accountant had been skimming small amounts from my account for years",
    "I found out the homeless shelter I volunteered at was a front for something else",
    "my childhood treehouse contained a time capsule from a group of kids 50 years ago",
    "I discovered my therapist had been writing a book about our sessions without my consent",
    "I found out my gardener was planting hidden cameras around my property",
    "my seemingly boring neighbor was actually a famous mystery novelist using a pen name",
    "I discovered my college roommate had been secretly paying my tuition all these years",
    "I found out my wife was the anonymous food critic who gave my restaurant one star",
    "my personal trainer was secretly competing against me in the same fitness competition",
    "I discovered my dentist was using my teeth mold to create replicas for a museum",
    "I found out my childhood best friend had been living two blocks away this whole time",
    "my babysitter was secretly training to become a professional athlete at night",
    "I discovered my landlord owned the entire block but pretended to be a regular tenant",
    "I found out my yoga teacher was a former CIA operative who taught meditation to spies",
    "my barista was secretly running a underground railroad for rescue animals",
    "I discovered my Uber ratings were being manipulated by a competitor driver",
    "I found out my wife had been secretly learning my native language to surprise me",
    "my seemingly random stranger at the coffee shop had been following my career for years",
    "I discovered my childhood bully had been anonymously donating to my charity",
    "I found out my company security guard was actually an off-duty detective solving our case",
    "my neighbor was secretly breeding exotic butterflies in his greenhouse",
    "I discovered my hairdresser was moonlighting as a FBI sketch artist",
    "I found out my wife was secretly bidding against me at an online auction",
    "my seemingly chaotic uncle was actually running a sophisticated investment portfolio",
    "I discovered my childhood pen pal lived three streets away and we never knew",
    "I found out my personal shopper was buying items for herself with my credit card",
    "my night shift security guard was secretly writing a bestselling thriller novel",
    "I discovered my dog walker was entering my dog in underground dog shows",
    "I found out my childhood friend had become a billionaire and never told anyone",
    "my seemingly ordinary mail route contained the largest drug bust in city history",
    "I discovered my wife was secretly coaching our kids competitive chess team",
    "I found out my dentist had been practicing new techniques on me without a license",
    "my childhood treehouse neighbor turned out to be my future business partner",
    "I discovered my gym manager was secretly a professional bodybuilding champion",
    "I found out my babysitter was a genius who had graduated college at age 14",
    "my night nurse had been secretly monitoring my health and saving my life every week",
    "my lawyer was secretly working for the other side of my divorce case",
    "I discovered my realtor was buying houses under my name without my knowledge",
    "my immigration attorney was taking bribes to delay cases",
    "I found out my insurance agent had been denying my claims on purpose",
    "my financial advisor was funneling my retirement into his own accounts",
    "I discovered my wedding planner was secretly in love with my spouse",
    "my travel agent was booking me in hotels she owned for commission",
    "I found out my tax preparer was claiming fake deductions and keeping the refunds",
    "my veterinarian was recommending unnecessary surgeries for profit",
    "I discovered my interior designer was selling my furniture at auction",
    "my wedding photographer was selling our photos to stock image sites",
    "I found out my driving instructor was bribing the DMV to pass students",
    "my notary was forging documents for a crime syndicate",
    "I discovered my home inspector was paid to hide critical defects",
    "I discovered my smart fridge was ordering food on its own",
    "I found out my AI assistant had been recording conversations I never started",
    "my robot vacuum was mapping my house and sending data to someone",
    "I discovered my fitness tracker predicted my heart attack three days before it happened",
    "my smart watch was secretly transmitting my location to my ex",
    "I found out my Alexa was playing sounds when nobody was home",
    "my self-driving car started taking me to places I never programmed",
    "I discovered my 3D printer was creating objects I never designed",
    "my smart TV was watching me more than I was watching it",
    "I found out my WiFi router was a secret government monitoring device",
    "my noise cancelling headphones were actually amplifying certain frequencies",
    "I discovered my electric toothbrush was collecting dental health data",
    "my smart mirror was taking photos every time I walked past",
    "I found out my GPS was deliberately giving me wrong directions",
    "my blender was secretly mining cryptocurrency",
    "I discovered my hospital mixed up my baby with another family",
    "I found out my surgeon was operating while intoxicated",
    "my therapist had been hypnotizing me to forget our sessions",
    "I discovered my dentist was keeping my extracted teeth for a collection",
    "my pharmacist was replacing my real medication with sugar pills",
    "I found out my nutritionist was being paid by a fast food company",
    "my personal trainer was secretly recording my body measurements",
    "I discovered my doctor was selling my blood to a research lab",
    "my eye doctor was deliberately worsening my prescription to sell more glasses",
    "I found out my hospital was billing me for procedures never performed",
    "my physical therapist was intentionally delaying my recovery",
    "I discovered my chiropractor was causing injuries to create repeat patients",
    "my dermatologist was using my skin samples for cosmetic testing",
    "I found out my dentist was selling my dental records to identity thieves",
    "my surgeon left a medical instrument inside me during operation",
    "I discovered my dog was leading a double life with another family",
    "I found out my cat had been bringing me gifts from three different houses",
    "my pet parrot was repeating conversations I never had at home",
    "I discovered my horse was being used for illegal racing at night",
    "my aquarium fish were communicating with the neighbors fish",
    "I found out my garden was growing plants from a seed company that went bankrupt 50 years ago",
    "my backyard squirrels were secretly working for the parks department",
    "I discovered my dog was the leader of a neighborhood dog pack",
    "my cat had been adopted by three other families on the same street",
    "I found out my chickens were laying eggs with messages inside",
    "my hamster was escaping every night and returning before morning",
    "I discovered my parrot knew secrets about my neighbors it should not know",
    "I found out my dog was a descendant of a famous show champion",
    "my backyard raccoons were running an organized food theft operation",
    "I discovered my personal trainer was a former Olympic athlete in hiding",
    "I found out my gym was holding secret midnight competitions",
    "my marathon training app was actually training me for a different race",
    "I discovered my yoga instructor was secretly judging my flexibility",
    "my swim coach had been timing me against an Olympic record holder",
    "I found out my sports team was being secretly filmed for a documentary",
    "my running group was actually a front for a secret society",
    "I discovered my CrossFit coach was using me as a test subject for new workouts",
    "my tennis partner was secretly recording our matches for analysis",
    "I found out my gym buddy was a professional bodybuilding coach",
    "my cycling instructor was deliberately making classes harder for me",
    "I discovered my sports massage therapist was also my competitors coach",
    "my boxing trainer had been training my opponent at the same time",
    "I found out my personal trainer was writing a book about my transformation",
    "my dance instructor was secretly entering me in competitions without telling me",
    "I discovered my paintings were being forged and sold as originals",
    "I found out my music teacher was secretly recording my lessons for an album",
    "my photography class was actually a cover for a spy recruitment program",
    "I discovered my pottery instructor was using my creations for her own gallery",
    "my writing group was actually competing against each other for a secret prize",
    "I found out my art supplies were being switched with expensive duplicates",
    "my acting coach was filming me for a secret documentary",
    "I discovered my calligraphy teacher was forging signatures on the side",
    "my sketch book was being photocopied and sold as printables",
    "I found out my vocal coach was using my voice samples for AI training",
    "I discovered my pottery wheel was rigged to record my technique",
    "my jewelry making teacher was copying my designs for her own line",
    "I found out my painting was worth millions but my teacher told me it was worthless",
    "my creative writing class was secretly a job interview for a publishing company",
    "I discovered my teacher was using me as a case study for her PhD thesis",
    "I found out my school principal was selling confidential student records",
    "my college roommate was secretly submitting assignments under my name",
    "I discovered my tutor was actually my birth mother",
    "my scholarship committee was tracking my every move for a reality show",
    "I found out my librarian was a famous author researching her next novel",
    "my school nurse was deliberately misdiagnosing students to pad her resume",
    "I discovered my driving instructor was giving lessons to my spouse at night",
    "my college professor was secretly dating three students simultaneously",
    "I found out my student loans were being paid by an anonymous donor who turned out to be my rival",
    "my school janitor was actually the former principal who lost everything",
    "I discovered my classroom had hidden cameras filming a reality show",
    "my academic advisor was deliberately steering me away from my dream career",
    "I found out my roommate was stealing my food and selling it to other students",
    "my chemistry teacher was running an underground lab after school",
    "I discovered my math tutor was using me to solve her research problems",
    "my history teacher was actually a time traveler collecting data",
    "I found out my college was selling my research data to corporations",
    "my boarding school headmaster was living a secret double life in the city",
    "I discovered my kindergarten teacher had been writing a tell-all book about students",
    # ── Wholesome / Kindness ──
    "a stranger paid for my groceries when I was about to lose everything",
    "my homeless neighbor turned out to be a millionaire testing the neighborhood",
    "I found out my mailman had been secretly fixing broken things around my house",
    "my cab driver drove me 200 miles for free because he recognized my mother",
    "the janitor at my school was secretly funding scholarships for poor students",
    "I discovered my boss had been paying my rent for six months without telling me",
    "my Ex came back not to reconcile but to return every gift I ever gave her",
    "a waitress gave me her last meal when the restaurant ran out of food",
    "my landlord lowered my rent and I did not find out until I saw the receipt",
    "the stranger sitting next to me on the plane turned out to be my future mentor",
    "my elderly neighbor left me her entire house because I mowed her lawn for 10 years",
    "I found a letter in a used book that changed my entire perspective on life",
    "my Uber driver was a therapist and helped me through a panic attack",
    "a random kid at the park returned my lost wallet with every dollar intact",
    # ── Overcoming Adversity ──
    "I was fired on my birthday and it was the best thing that ever happened to me",
    "my wife left me with three kids and no money but I rebuilt everything",
    "I failed my medical board exam four times before I finally passed",
    "my house burned down and my community rebuilt it while I was in the hospital",
    "I was told I would never walk again but I crossed a marathon finish line",
    "my business went bankrupt and I started over with nothing but a laptop",
    "I lost my sight at 25 and discovered a talent I never knew I had",
    "my cancer diagnosis came the same week I got promoted",
    "I was homeless for two years before I became a CEO",
    "my divorce left me broken but it led me to my soulmate",
    "I was rejected from every college I applied to and now I teach at one",
    "my accent was mocked in school but it became my superpower in business",
    "I grew up in foster care and just adopted my first child",
    "my stutter almost destroyed my confidence until I found stand-up comedy",
    "I was told my art was worthless but a stranger just bought my first painting",
    # ── Horror / Supernatural ──
    "I woke up at 3am to someone whispering my name through the baby monitor",
    "my new apartment came with a mirror that showed a different reflection",
    "I found footprints in the snow leading to my door but none leading away",
    "my daughter kept talking about her imaginary friend who knew things she should not",
    "I discovered my house was built on top of something that was never meant to be found",
    "my reflection in the bathroom mirror smiled when I did not",
    "I heard scratching inside my walls every night at exactly 2:47am",
    "my neighbors all moved out on the same day and nobody would tell me why",
    "I found a VHS tape in my basement that showed my house from the inside",
    "my sleep paralysis started showing me the same figure every single night",
    "I bought a used diary and the previous owner described events that had not happened yet",
    "my phone started receiving texts from a number that belonged to someone who died in 2019",
    "the old well on my property was sealed for a reason nobody wanted to explain",
    "I discovered the previous tenant left because of something still living in the attic",
    "my car GPS keeps directing me to an address that does not exist on any map",
    # ── Justice / Karma ──
    "my manager stole my idea and got promoted but I had the receipts",
    "the woman who falsely accused me of harassment just got caught on camera",
    "my ex-business partner tried to bankrupt me but the judge saw through it",
    "I discovered my insurance company had been denying claims for years",
    "the landlord who evicted my family just got arrested for fraud",
    "my bully from school just applied for a job at my company",
    "the teacher who failed me was caught plagiarizing student work",
    "my neighbor who harassed me for years just got a taste of her own medicine",
    "the company that scammed my parents just got shut down by the FBI",
    "my cheating Ex just found out I am dating his boss",
    "the politician who ruined my town just got exposed on live television",
    "my corrupt boss fired me but I just bought the company",
    "the doctor who misdiagnosed me lost his license after I reported him",
    "my toxic manager got transferred to the worst branch after I left",
    "the person who stole my identity just got caught because of a traffic ticket",
    # ── Family / Bonds ──
    "my father never said he was proud of me until the day he could not speak",
    "I found a box of letters my mother wrote me but never sent",
    "my brother and I fought for years over nothing and then I found his secret",
    "my grandmother left me a recipe book with a map hidden inside",
    "I discovered my quiet father was a war hero and nobody in the family knew",
    "my sister and I were separated at birth and just found each other on TikTok",
    "my grandfather's old watch contained a message meant for someone 50 years later",
    "I found out my parents sold their house to pay for my surgery",
    "my daughter drew a picture of our family and included someone I had forgotten about",
    "my mother worked three jobs so I could play soccer and I never knew until now",
    "my uncle drove 12 hours to surprise me at my college graduation",
    "I discovered my dad had been secretly following my baseball career from a distance",
    "my grandmother's dying wish was something I could actually fulfill",
    "my son saved up his own money to buy me a birthday present",
    "I found out my sister was the anonymous donor who paid for my therapy",
    # ── Self-Discovery / Identity ──
    "I took a DNA test and found out I have a twin I never knew existed",
    "my entire childhood was a lie but the truth made me stronger",
    "I discovered the accent I was mocked for was actually a rare dialect",
    "my family always said I was adopted as a joke but it turned out to be real",
    "I found out I was a descendant of someone historical I had been studying",
    "my birth certificate had the wrong name and I found out why 30 years later",
    "I discovered my talent for languages only after moving to a country where nobody spoke mine",
    "my mother told me my father was dead but I just saw him on the news",
    "I found old home videos that showed a version of my childhood I had forgotten",
    "my mirror reflection started feeling like it belonged to someone else",
    "I was raised thinking I was an only child and just found my brother on Facebook",
    "my passion for cooking started the day I found my grandmother's hidden cookbook",
    "I discovered the reason I always felt different was because I was undiagnosed",
    "my childhood drawings predicted things that actually happened later in life",
    "I found a journal I wrote at age 10 that described my future in detail",
    # ── Second Chances / Redemption ──
    "my ex-husband came back after 10 years with a proposal I never expected",
    "I forgave the person who ruined my life and it freed me",
    "my estranged daughter just called me for the first time in 5 years",
    "the bully from my childhood just apologized out of nowhere",
    "I gave my cheating wife a second chance and she saved my life",
    "my father who abandoned me just showed up at my wedding",
    "I reconnected with my best friend after a fight that lasted 15 years",
    "my old rival just became my biggest supporter",
    "I forgave myself for something I did ten years ago and everything changed",
    "my mother and I stopped talking for years but one letter brought us back",
    "I gave my reckless brother a job and he turned my company around",
    "my ex-best friend just saved my life and I did not know how to react",
    "the woman I wronged in college just recommended me for my dream job",
    "I tracked down the person I hurt in high school and asked for forgiveness",
    "my son forgave me for missing his childhood and we started over",
    # ── Unexpected Friendships ──
    "my worst enemy became my best friend after we got stuck in an elevator",
    "I found out my online gaming buddy lives three houses down",
    "my retirement neighbor and I started a business together and it took off",
    "my rival at work and I bonded over the same secret hobby",
    "I discovered my dog was visiting the same公园 as another dog and their owner became my best friend",
    "my seatmate on a 14-hour flight became my business partner",
    "I met a stranger at a coffee shop who turned out to be my pen pal from childhood",
    "my grumpy coworker and I were forced to team up and now we are inseparable",
    "I found out the person I argue with online every day goes to my gym",
    "my new neighbor turned out to be my childhood imaginary friend's real inspiration",
    "I bonded with my Uber driver over a shared secret from high school",
    "my worst college professor became my most important mentor",
    "I met a stranger at the laundromat who changed my career trajectory",
    "my rival chess player and I started a podcast together",
    "I discovered my cat had been visiting the neighbor and now we are family friends",
    # ── Life-Changing Moments ──
    "I almost missed my flight but the delay saved my life",
    "I found a $50 bill on the ground and it led to the biggest opportunity of my life",
    "a wrong number text changed everything I thought I knew about my family",
    "I was about to give up on my dream when a stranger handed me a business card",
    "the traffic jam I hated turned into the day I met my wife",
    "I lost my job on Monday and found my calling by Friday",
    "a broken elevator forced me into a conversation that changed my career",
    "I was going to donate my car but found a letter hidden in the trunk",
    "the restaurant that got my order wrong accidentally introduced me to my best friend",
    "I was about to swipe left but something made me stop",
    "a rainstorm forced me into a bookshop where I found a book written about me",
    "I missed my bus and the next one had a seat next to my future business partner",
    "my phone died at the worst moment and it turned out to be the best thing",
    "I was about to quit piano but a neighbor heard me practicing and offered lessons",
    "the flat tire I cursed led me to a mechanic who became my lifelong friend",
    # ── Emotional Reveals ──
    "my mother kept a secret about my birth for 35 years and I found the letter",
    "my grandfather's dying words unlocked a mystery I never knew existed",
    "I discovered my wife had been writing a novel about our marriage without telling me",
    "my best friend's wedding speech revealed something about my own childhood",
    "I found out my daughter had been saving money to buy me a gift I desperately needed",
    "my mother's recipe book contained letters from someone I had never heard of",
    "I discovered my quiet neighbor was the one leaving anonymous gifts on my porch",
    "my father's old camera contained photos that told a story he never shared",
    "I found out my son had been secretly learning sign language to communicate with me",
    "my grandmother's jewelry box contained a note that changed our entire family history",
    "I discovered my wife had been planning a surprise that I accidentally ruined",
    "my best friend secretly recorded our friendship and made a documentary",
    "I found out my mother had been visiting my grave every year thinking I was dead",
    "my father left a voicemail I never heard that explains everything",
    "I discovered my childhood home had a time capsule with a message meant for me",
    # ── Workplace / Career ──
    "my intern turned out to be the CEO's daughter and she changed my career",
    "I discovered my company's coffee machine was the source of everyone's best ideas",
    "my quiet cubicle neighbor was secretly a famous podcaster",
    "I found out my promotion was blocked because someone was jealous of my marriage",
    "my worst meeting turned into the opportunity that changed my entire industry",
    "I discovered my company had been testing a product on employees without consent",
    "my resignation letter accidentally got sent to the entire company",
    "I found out my salary was capped because of a policy from 1987",
    "my boss and I had the same secret hobby and it changed our relationship",
    "I discovered my coworker was writing a tell-all book about our workplace",
    "my LinkedIn post went viral and my boss asked me to delete it",
    "I found out my company was about to be sold and I had 24 hours to decide",
    "my office prank backfired and revealed a hidden camera in the building",
    "I discovered my team had been covering for my mistakes for two years",
    "my performance review contained a secret code that led to a treasure hunt",
    # ── Relationships / Love ──
    "my first love showed up at my door 20 years later with a revelation",
    "I discovered my arranged marriage turned into the greatest love story",
    "my wife and I renewed our vows and the officiant revealed a secret about us",
    "I found out my husband had been writing me love letters every day for 30 years",
    "my girlfriend and I discovered we had met as children but neither remembered",
    "I found out my partner was the anonymous caller who saved my life",
    "my wife's last wish was something I should have done years ago",
    "I discovered my spouse had been secretly learning my love language",
    "my husband and I were separated by war and reunited by a social media post",
    "I found out my partner proposed because of something I said in my sleep",
    "my wife kept a journal of every happy moment we shared for 25 years",
    "I discovered my boyfriend had been secretly building me a house",
    "my girlfriend and I found out we were on the same plane 10 years before we met",
    "I found out my partner had been writing letters to our future children",
    "my husband surprised me with something I mentioned once 15 years ago",
    # ── Mystery / Investigation ──
    "I found a locked box in my grandmother's attic and the key was around her neck",
    "my old neighbor's disappearance was solved by a photo I found in my basement",
    "I discovered a hidden message in a painting I bought at a thrift store",
    "my family's old letter revealed a mystery that had been unsolved for 50 years",
    "I found a map in a used book that led to something real",
    "my grandmother's locket contained a photo of someone nobody in the family recognized",
    "I discovered my childhood drawings matched a cold case from the 1990s",
    "my old diary entries predicted events that were happening in real time",
    "I found a mysterious key in my new house and it opened something I was not ready for",
    "my grandfather's military records revealed a secret mission nobody knew about",
    "I discovered the mysterious caller from my childhood was actually trying to help",
    "my old phone contained photos of a place I had never been but recognized",
    "I found a letter addressed to me that was postmarked 20 years before I was born",
    "my grandmother's recipe book had a code hidden in the margins",
    "I discovered my childhood imaginary friend was based on a real missing person",
    # ── MOTHER-IN-LAW DRAMA ──
    "my mother in law stole our wedding money and used it to renovate her house",
    "my mother in law tried to name our baby without asking us",
    "my mother in law left me out of the family photo on purpose",
    "my mother in law told my kids I was not their real mom",
    "my mother in law secretly met my husband ex and still invites her to family dinners",
    "my mother in law gave my husband an ultimatum choose me or her",
    "my mother in law moved into our house without asking and refuses to leave",
    "my mother in law told me I was not good enough for her son at our wedding",
    # ── SIBLING RIVALRY + INHERITANCE WARS ──
    "my sister stole my boyfriend and announced her pregnancy at my birthday party",
    "my brother sold our dead parents house without telling me and kept all the money",
    "my sister deliberately ruined my wedding dress the night before the ceremony",
    "my brother took out a loan in my name and ruined my credit score",
    "my sister told my husband about my past on purpose to break us up",
    "my brother was secretly dating my best friend behind my back for 2 years",
    "my sister faked a medical emergency to steal attention from my graduation",
    "my brother was embezzling money from our family business for 5 years",
    "my father changed his will 2 weeks before he died and left everything to my brother",
    "my mother left the entire estate to my sister and nothing to me after 30 years of care",
    # ── WEDDING DRAMA + IN-LAW BETRAYAL ──
    "my sister in law livestreamed our wedding to my husband ex wife",
    "my mother in law wore a white dress to my wedding and tried to be the center of attention",
    "my sister in law announced her pregnancy during my wedding speech",
    "my mother in law tried to change our wedding menu without telling us",
    "my father in law refused to walk me down the aisle because I was not good enough",
    "my sister in law invited 20 extra guests to our wedding without permission",
    "my mother in law gave a toast about how her marriage was better than ours",
    "my brother in law tried to sabotage our honeymoon by booking the same hotel",
    # ── PARENTAL FAVORITISM ──
    "my parents paid for my sisters college but told me to take out loans",
    "my mother gave my childhood bedroom to my brother without asking me",
    "my father walked my sister down the aisle but refused to walk mine",
    "my parents sold my childhood home and did not tell me until it was done",
    "my mother told me I was the mistake child and my brother was the planned one",
    "my father left me nothing in his will because I was not his favorite",
    "my parents made me pay rent at 16 while my brother lived for free at 25",
    "my mother skipped my graduation to go to my sisters dance recital",
    # ── STEPFAMILY DRAMA ──
    "my stepmom tried to replace my dead mother and I told her the truth at Christmas",
    "my stepfather sold my mothers wedding ring to buy himself a boat",
    "my stepsister told everyone I was not really family at Thanksgiving dinner",
    "my stepmom cut me out of the family photo and replaced me with her own daughter",
    "my stepmother told my children their real grandmother was dead",
    "my stepsiblings stole my inheritance by forging documents",
    # ── ELDERLY PARENT CARE DISPUTES ──
    "my sister refused to help care for our sick mother and then demanded her inheritance",
    "my brother moved our father into a nursing home without asking the family",
    "my sister stole money from our mothers account to pay for her vacation",
    "my brother sold our fathers car while he was in the hospital",
    "my sister put our mother in a cheap facility but kept the money for her care",
    # ── FAMILY BUSINESS CONFLICTS ──
    "my brother fired me from our family restaurant and hired his friend instead",
    "my father made my brother CEO and told me I was not business material",
    "my sister was stealing from our family store for years and blamed me",
    "my parents signed the business over to my brother without telling me",
    # ── CHRISTMAS + HOLIDAY DRAMA ──
    "my mother in law uninvited me from Christmas because I was not pregnant yet",
    "my sister announced her engagement at my Christmas party to steal my spotlight",
    "my father in law gave me a gym membership as a Christmas present",
    "my mother in law gave everyone gifts except me and said I was not family yet",
    "my brother started a fight at Thanksgiving and my mother blamed me",
    "my mother gave my children less presents than my brothers children on purpose",
    # ── MONEY + FINANCIAL FAMILY DRAMA ──
    "my parents lent my brother 50000 but refused to help me with college tuition",
    "my sister borrowed money and then told the family I was greedy when I asked for it back",
    "my parents paid for my sisters wedding but said they could not afford mine",
    "my brother moved back home at 30 and my parents made me give up my bedroom",
    "my parents changed the locks on me after I asked for my inheritance early",
    "my sister asked me to be her maid of honor but said she could not pay me back for the dress",
]

logging.basicConfig(
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("autopilot")
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

# ── Global state ──
autopilot_running = False
stats = {
    "total_generated": 0,
    "total_audio": 0,
    "total_video": 0,
    "total_youtube": 0,
    "total_errors": 0,
    "last_theme": "",
    "last_score": 0,
    "current_stage": "idle",
}


def _seed_stats_from_db():
    """Load lifetime counters from the local database.

    The counters used to live only in memory, so every bot restart reported
    "0 uploaded" even after hundreds of completed renders.
    """
    try:
        import sqlite3
        from pathlib import Path

        db_path = Path(__file__).resolve().parent / "app" / "storage" / "kokoro.db"
        if not db_path.exists():
            return
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5)
        try:
            generated = conn.execute(
                "select count(*) from render_jobs where status='completed'"
            ).fetchone()[0]
            audio = conn.execute(
                "select count(*) from generated_audio where status='ready'"
            ).fetchone()[0]
            youtube = conn.execute(
                "select count(*) from youtube_uploads "
                "where status in ('uploaded', 'completed')"
            ).fetchone()[0]
        finally:
            conn.close()
        stats["total_generated"] = int(generated or 0)
        stats["total_audio"] = int(audio or 0)
        stats["total_youtube"] = int(youtube or 0)
        log.info(
            "[Stats] Seeded from DB: %s stories, %s audio, %s uploaded",
            stats["total_generated"],
            stats["total_audio"],
            stats["total_youtube"],
        )
    except Exception as e:
        log.warning(f"[Stats] Could not seed counters from DB: {e}")


_seed_stats_from_db()

# Track story completion state to prevent overlap
stories_in_progress: set[str] = set()
stories_completed: set[str] = set()
story_started_at: dict[str, float] = {}
STALE_STORY_TIMEOUT = 20 * 60


def progress_bar(percent, length=10):
    filled = int(length * percent / 100)
    return f"[{'█' * filled}{'░' * (length - filled)}] {percent}%"


def pick_unused_theme():
    """Pick a random theme that has not been used before (via API dedup check)."""
    candidates = list(PROMPTS)
    random.shuffle(candidates)
    for theme in candidates:
        try:
            import urllib.request

            req = urllib.request.Request(
                f"{BACKEND_URL}/api/forge/check-theme",
                data=json.dumps({"theme": theme}).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read())
                if not result.get("is_used", False):
                    return theme
        except Exception:
            return theme
    return random.choice(PROMPTS)


async def api_post(path, data, timeout=600, retry_safe=True):
    """POST to the local backend with bounded recovery for socket resets."""
    attempts = 3 if retry_safe else 1
    timeout_config = aiohttp.ClientTimeout(total=timeout, connect=20, sock_read=timeout)
    last_error = None

    for attempt in range(attempts):
        try:
            connector = aiohttp.TCPConnector(
                force_close=True, enable_cleanup_closed=True
            )
            async with aiohttp.ClientSession(connector=connector) as session:
                async with session.post(
                    f"{BACKEND_URL}{path}",
                    json=data,
                    timeout=timeout_config,
                ) as response:
                    if response.status != 200:
                        text = await response.text()
                        raise Exception(
                            f"{path} returned {response.status}: {text[:200]}"
                        )
                    return await response.json()
        except asyncio.TimeoutError as exc:
            last_error = f"timeout after {timeout}s"
        except (
            aiohttp.ClientOSError,
            aiohttp.ServerDisconnectedError,
            ConnectionResetError,
        ) as exc:
            last_error = f"transient connection error: {exc}"
        except Exception as exc:
            raise Exception(f"{path} request failed: {exc}") from exc

        if attempt < attempts - 1:
            delay = 2**attempt
            log.warning(
                "[Telegram] %s failed (%s), retrying in %ds (%d/%d)",
                path,
                last_error,
                delay,
                attempt + 1,
                attempts,
            )
            await asyncio.sleep(delay)

    raise Exception(f"{path} request failed: {last_error}")


async def api_get(path, timeout=30):
    async with aiohttp.ClientSession() as s:
        async with s.get(
            f"{BACKEND_URL}{path}", timeout=aiohttp.ClientTimeout(total=timeout)
        ) as r:
            if r.status != 200:
                text = await r.text()
                raise Exception(f"{path} returned {r.status}: {text[:200]}")
            return await r.json()


async def api_get_file(path, timeout=120):
    async with aiohttp.ClientSession() as s:
        async with s.get(
            f"{BACKEND_URL}{path}", timeout=aiohttp.ClientTimeout(total=timeout)
        ) as r:
            if r.status != 200:
                raise Exception(f"File download failed: {r.status}")
            return await r.read()


async def send_status(context, text):
    if not AUTOPILOT_CHAT_ID:
        return
    try:
        await context.bot.send_message(chat_id=int(AUTOPILOT_CHAT_ID), text=text)
    except Exception as e:
        log.error(f"Failed to send status: {e}")


async def send_video_to_telegram(context, render_id, filename, hook, score, duration):
    if not AUTOPILOT_CHAT_ID:
        return
    temp_path = None
    try:
        file_bytes = await api_get_file(f"/api/renders/{render_id}/file", timeout=120)
        temp_path = os.path.join(tempfile.gettempdir(), filename)
        with open(temp_path, "wb") as f:
            f.write(file_bytes)
        caption = f"Hook: {hook}\nScore: {score}/100 | Duration: {duration:.1f}s"
        upload_error = None
        for attempt in range(3):
            try:
                # Use the Telegram HTTP API directly for large media. The
                # python-telegram-bot request pool can retain a shorter
                # read timeout than the per-call override on Windows.
                with open(temp_path, "rb") as f:
                    form = aiohttp.FormData()
                    form.add_field("chat_id", str(AUTOPILOT_CHAT_ID))
                    form.add_field("caption", caption)
                    form.add_field("supports_streaming", "true")
                    form.add_field(
                        "video",
                        f,
                        filename=filename,
                        content_type="video/mp4",
                    )
                    timeout = aiohttp.ClientTimeout(
                        total=600, connect=60, sock_connect=60, sock_read=600
                    )
                    async with aiohttp.ClientSession() as session:
                        async with session.post(
                            f"https://api.telegram.org/bot{BOT_TOKEN}/sendVideo",
                            data=form,
                            timeout=timeout,
                        ) as response:
                            response_data = await response.json(content_type=None)
                            if response.status != 200 or not response_data.get("ok"):
                                raise RuntimeError(
                                    f"Telegram sendVideo failed: {response.status} "
                                    f"{str(response_data)[:300]}"
                                )
                log.info("[Telegram] Video uploaded on attempt %d", attempt + 1)
                return
            except (
                TimedOut,
                NetworkError,
                aiohttp.ClientError,
                asyncio.TimeoutError,
            ) as exc:
                upload_error = exc
                log.warning(
                    "[Telegram] Video upload timed out on attempt %d/3: %s",
                    attempt + 1,
                    type(exc).__name__,
                )
                if attempt < 2:
                    await asyncio.sleep(2**attempt)

        # Telegram may reject large/slow video uploads while still accepting
        # the same file as a document, which preserves delivery for the user.
        log.warning(
            "[Telegram] Retrying failed video upload as a document: %s", upload_error
        )
        with open(temp_path, "rb") as f:
            form = aiohttp.FormData()
            form.add_field("chat_id", str(AUTOPILOT_CHAT_ID))
            form.add_field("caption", caption)
            form.add_field("document", f, filename=filename, content_type="video/mp4")
            timeout = aiohttp.ClientTimeout(
                total=600, connect=60, sock_connect=60, sock_read=600
            )
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument",
                    data=form,
                    timeout=timeout,
                ) as response:
                    response_data = await response.json(content_type=None)
                    if response.status != 200 or not response_data.get("ok"):
                        raise RuntimeError(
                            f"Telegram sendDocument failed: {response.status} "
                            f"{str(response_data)[:300]}"
                        )
        log.info("[Telegram] Video delivered as a document")
    except Exception as e:
        log.error(f"Failed to send video: {e}")
    finally:
        if "temp_path" in locals():
            try:
                os.unlink(temp_path)
            except FileNotFoundError:
                pass


async def run_one_pipeline(context):
    global stats

    theme = pick_unused_theme()
    stats["last_theme"] = theme
    iteration = stats["total_generated"] + 1

    # Check if a story is already in progress for this theme
    if theme in stories_in_progress:
        log.info(f"[Telegram] Story already in progress for theme: {theme[:60]}")
        await send_status(context, f"#{iteration} Story already in progress. Skipping.")
        return False

    try:
        # Mark story as in progress
        stories_in_progress.add(theme)
        story_started_at[theme] = asyncio.get_running_loop().time()

        # ── Story ──
        stats["current_stage"] = "story"
        await send_status(
            context,
            f"{progress_bar(5)} #{iteration}\nTheme: {theme}\nGenerating story...",
        )
        story_result = await api_post(
            "/api/forge/run-all", {"theme": theme}, timeout=900, retry_safe=False
        )

        script = story_result.get("final_script", "")
        score = story_result.get("quality_score", 0)
        words = story_result.get("word_count", 0)
        duration = story_result.get("estimated_duration", 0)
        hook = story_result.get("selected_hook", {})
        hook_text = hook.get("text", "N/A") if hook else "N/A"
        classification = story_result.get("classification", {})
        category = classification.get("category", "N/A") if classification else "N/A"

        if not script or len(script) < 50:
            stats["total_errors"] += 1
            await send_status(context, f"#{iteration} Story failed. Skipping.")
            stories_in_progress.discard(theme)
            stories_completed.add(theme)
            return False

        stats["total_generated"] += 1
        stats["last_score"] = score

        # Detect lead gender from actual script content (more reliable than classification)
        lead_gender = detect_lead_gender(script, theme)
        voice = VOICE_FEMALE if lead_gender == "female" else VOICE_MALE

        await send_status(
            context,
            f"{progress_bar(30)} #{iteration}\n"
            f"Script: {words} words (~{duration}s) | Score: {score}/100\n"
            f"Lead: {lead_gender} | Voice: {voice}\n"
            f"Hook: {hook_text}",
        )

        # ── Audio ──
        stats["current_stage"] = "audio"
        tts_result = await api_post(
            "/api/tts/generate",
            {
                "text": script,
                "voice": voice,
                "mode": "shorts",
                "preset": "storytelling",
                "tone": "natural",
                "use_enhancement": True,
                "enhancement_level": "balanced",
            },
            timeout=300,
        )

        audio_id = tts_result.get("id", "")
        audio_duration = tts_result.get("duration", 0)
        if not audio_id:
            stats["total_errors"] += 1
            await send_status(context, f"#{iteration} Audio failed. Skipping.")
            return False
        stats["total_audio"] += 1

        # ── Video ──
        stats["current_stage"] = "video"
        render_result = await api_post(
            "/api/renders/",
            {
                "project_id": PROJECT_ID,
                "generated_audio_id": audio_id,
                "video_folders": DEFAULT_VIDEO_FOLDERS,
            },
            timeout=30,
        )
        render_id = render_result.get("id", "")
        if not render_id:
            stats["total_errors"] += 1
            return False

        for i in range(120):
            await asyncio.sleep(5)
            status_result = await api_get(f"/api/renders/{render_id}", timeout=10)
            status = status_result.get("status", "")
            if status == "completed":
                break
            elif status == "failed":
                stats["total_errors"] += 1
                return False
        else:
            stats["total_errors"] += 1
            return False

        output = await api_get(f"/api/renders/{render_id}/output", timeout=10)
        render_output_id = output.get("id", "")
        video_filename = output.get("video_filename", "")
        stats["total_video"] += 1

        # ── YouTube ──
        stats["current_stage"] = "youtube"
        youtube_uploaded = False
        yt_reason = ""
        try:
            yt_status = await api_get("/api/youtube/status", timeout=10)
            yt_connected = yt_status.get("connected", False)
            if not yt_connected:
                auth_url = ""
                try:
                    auth_resp = await api_get("/api/youtube/auth", timeout=10)
                    auth_url = (auth_resp or {}).get("auth_url", "")
                except Exception:
                    pass
                yt_reason = (
                    "YouTube not connected - authorize once:\n" + auth_url
                    if auth_url
                    else "YouTube not connected (re-authorize at /api/youtube/auth)"
                )
        except Exception as e:
            yt_connected = False
            yt_reason = f"status check failed: {e}"

        # Check if quota is already known to be exceeded
        quota_hit = False
        try:
            queue_info = await api_get("/api/youtube/queue", timeout=10)
            quota_hit = queue_info.get("quota_exceeded", False)
            if quota_hit:
                yt_reason = "YouTube quota exceeded"
        except Exception:
            pass

        if yt_connected and not quota_hit:
            try:
                upload_result = await api_post(
                    "/api/youtube/upload",
                    {
                        "render_output_id": render_output_id,
                        "privacy_status": "public",
                        "auto_metadata": True,
                        "topic": theme,
                        "niche": NICHE,
                    },
                    timeout=30,
                )
                upload_id = upload_result.get("id", "")

                if upload_id:
                    # Uploads run in the background; 6x5s (30s) was too short and
                    # reported failure for uploads that succeeded moments later.
                    for i in range(24):
                        await asyncio.sleep(5)
                        upload_status = await api_get(
                            f"/api/youtube/uploads/{upload_id}", timeout=10
                        )
                        yt_upload_status = upload_status.get("status", "")

                        # The uploader writes "uploaded"; older rows and other
                        # callers use "completed". Accept both.
                        if yt_upload_status in ("completed", "uploaded"):
                            video_url = upload_status.get("video_url", "")
                            stats["total_youtube"] += 1
                            youtube_uploaded = True
                            await send_status(
                                context,
                                f"{progress_bar(100)} #{iteration} DONE!\n"
                                f"Hook: {hook_text}\n"
                                f"Score: {score}/100\n"
                                f"YouTube: {video_url}\n"
                                f"Total uploaded: {stats['total_youtube']}",
                            )
                            break

                        elif yt_upload_status == "failed":
                            error_msg = upload_status.get("error_message", "")
                            yt_reason = error_msg or "upload failed"
                            if (
                                "exceeded" in error_msg.lower()
                                or "quota" in error_msg.lower()
                            ):
                                quota_hit = True
                                log.warning("[YT] Upload quota exceeded")
                            break

                        if i >= 23:
                            log.warning(
                                f"[YT] Upload {upload_id} still pending after "
                                f"{(i + 1) * 5}s; giving up on this poll cycle"
                            )
                            yt_reason = (
                                f"upload {upload_id} still "
                                f"'{yt_upload_status or 'unknown'}' after 120s"
                            )
            except Exception as e:
                log.error(f"YouTube upload error: {e}")
                yt_reason = yt_reason or f"upload request failed: {e}"

        if not youtube_uploaded:
            # YouTube upload failed/skipped — mark story complete without video delivery
            log.warning(
                "[YT] YouTube upload not completed (%s); story marked complete "
                "without video delivery",
                yt_reason or "no upload attempted",
            )
            await send_status(
                context,
                f"#{iteration} complete! YouTube upload did not deliver video.\n"
                f"Reason: {yt_reason or 'unknown'}\n"
                f"Total: {stats['total_generated']} stories | {stats['total_youtube']} uploaded",
            )
        else:
            await send_status(
                context,
                f"{progress_bar(100)} #{iteration} DONE!\n"
                f"Hook: {hook_text}\n"
                f"Score: {score}/100\n"
                f"YouTube: {video_url}\n"
                f"Total uploaded: {stats['total_youtube']}",
            )

        # ── Story completion tracking ──
        # total_errors is cumulative - zeroing it here made /stats always
        # report 0 errors regardless of how many stories had failed.
        stories_completed.add(theme)
        stats["current_stage"] = "completed"

        return True

    except Exception as e:
        log.error(f"Pipeline error: {e}", exc_info=True)
        stats["total_errors"] += 1
        return False
    finally:
        stories_in_progress.discard(theme)
        story_started_at.pop(theme, None)


async def autopilot_loop(context):
    global autopilot_running, stats

    await send_status(
        context,
        "AUTO-PILOT STARTED\n"
        f"Male: {VOICE_MALE} | Female: {VOICE_FEMALE}\n"
        f"No daily upload limit\n"
        f"Themes are deduplicated automatically\n"
        f"Type /stop to stop | /status for stats\n"
        f"In-progress: {len(stories_in_progress)} | Completed: {len(stories_completed)}",
    )

    while autopilot_running:
        now = asyncio.get_running_loop().time()
        stale_themes = [
            theme
            for theme in stories_in_progress
            if now - story_started_at.get(theme, now) > STALE_STORY_TIMEOUT
        ]
        for stale_theme in stale_themes:
            stories_in_progress.discard(stale_theme)
            story_started_at.pop(stale_theme, None)
            stats["total_errors"] += 1
            log.error(
                "[Telegram] Cleared stale story after %d seconds: %s",
                STALE_STORY_TIMEOUT,
                stale_theme[:80],
            )

        # Check for stories already in progress
        if stories_in_progress:
            log.info(
                f"[Telegram] {len(stories_in_progress)} story(ies) in progress, waiting..."
            )
            await asyncio.sleep(30)
            continue

        # Run pipeline immediately
        stats["current_stage"] = "running"
        success = await run_one_pipeline(context)

        if not autopilot_running:
            break

        # Small delay between runs (only if story completed successfully)
        if success:
            await asyncio.sleep(15)
        else:
            await asyncio.sleep(30)

    stats["current_stage"] = "stopped"
    await send_status(
        context,
        "AUTO-PILOT STOPPED\n\n"
        f"Stats: {stats['total_generated']} stories | "
        f"{stats['total_youtube']} uploaded | {stats['total_errors']} errors\n"
        f"In-progress: {len(stories_in_progress)} | Completed: {len(stories_completed)}",
    )


# ── Command Handlers ──


async def safe_reply(update: Update, text: str) -> bool:
    """Reply without turning a transient Telegram timeout into an update error."""
    if not update.message:
        return False
    for attempt in range(2):
        try:
            await update.message.reply_text(text)
            return True
        except (TimedOut, NetworkError) as exc:
            if attempt == 0:
                log.warning("[Telegram] Reply failed, retrying: %s", type(exc).__name__)
                await asyncio.sleep(1)
            else:
                log.error("[Telegram] Reply failed after retry: %s", type(exc).__name__)
    return False


async def authorized_command(update: Update) -> bool:
    """Restrict control commands when TELEGRAM_CHAT_ID is configured."""
    if not AUTHORIZED_CHAT_ID or not update.effective_chat:
        return True
    if str(update.effective_chat.id) == AUTHORIZED_CHAT_ID:
        return True
    await safe_reply(update, "This bot is restricted to its configured control chat.")
    log.warning("[Telegram] Rejected command from chat %s", update.effective_chat.id)
    return False


async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global autopilot_running, AUTOPILOT_CHAT_ID
    if not await authorized_command(update):
        return
    AUTOPILOT_CHAT_ID = str(update.effective_chat.id)

    if autopilot_running:
        await safe_reply(update, "Already running. /stop to stop, /status for stats.")
        return

    autopilot_running = True
    asyncio.create_task(autopilot_loop(context))
    await safe_reply(
        update,
        "AUTO-PILOT STARTED\n\n"
        "Runs immediately:\n"
        "Story -> Audio -> Video -> YouTube\n\n"
        "/stop — Stop\n/status — Stats",
    )


async def stop_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global autopilot_running
    if not await authorized_command(update):
        return
    if not autopilot_running:
        await safe_reply(update, "Not running.")
        return
    autopilot_running = False
    await safe_reply(update, "Stopping...")


async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await authorized_command(update):
        return
    quota_info = ""
    try:
        queue_info = await api_get("/api/youtube/queue", timeout=5)
        quota_pending = queue_info.get("quota_queue_size", 0)
        quota_hit = queue_info.get("quota_exceeded", False)
        if quota_hit:
            quota_info = f"\nYouTube Quota: EXCEEDED ({quota_pending} pending retry)"
        elif quota_pending > 0:
            quota_info = f"\nYouTube Quota: OK ({quota_pending} pending from earlier)"
    except Exception:
        pass

    await safe_reply(
        update,
        f"Status: {stats['current_stage'].upper()}\n\n"
        f"Stories: {stats['total_generated']}\n"
        f"Audio: {stats['total_audio']}\n"
        f"Video: {stats['total_video']}\n"
        f"YouTube: {stats['total_youtube']}\n"
        f"Errors: {stats['total_errors']}\n"
        f"{quota_info}\n\n"
        f"Last: {stats['last_theme'][:50]}\n"
        f"Score: {stats['last_score']}/100\n\n"
        f"{'Running' if autopilot_running else 'Stopped'}",
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await authorized_command(update):
        return
    await safe_reply(
        update,
        "AUTO-PILOT COMMANDS:\n\n"
        "/start — Start (runs immediately)\n"
        "/stop — Stop\n"
        "/status — Stats\n"
        "/help — This message",
    )


async def telegram_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    error = context.error
    if isinstance(error, (TimedOut, NetworkError)):
        log.warning("[Telegram] Transient network error: %s", type(error).__name__)
    else:
        log.error("[Telegram] Update failed", exc_info=error)


def main():
    if not BOT_TOKEN:
        print("Set TELEGRAM_BOT_TOKEN env var.")
        sys.exit(1)

    print(f"Backend: {BACKEND_URL}")
    print("No daily upload limit. Themes are deduplicated.")
    print("Starting auto-pilot bot...")

    request = HTTPXRequest(
        connection_pool_size=32,
        read_timeout=120.0,
        write_timeout=600.0,
        connect_timeout=30.0,
        pool_timeout=30.0,
        media_write_timeout=600.0,
    )
    app = Application.builder().token(BOT_TOKEN).request(request).build()
    app.add_error_handler(telegram_error_handler)
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("stop", stop_cmd))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("help", help_cmd))

    print("Bot running. /start to begin.")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
