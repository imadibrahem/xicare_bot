
from presidio_analyzer import AnalyzerEngine, PatternRecognizer, Pattern, RecognizerResult
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig
from langdetect import detect
import re
import warnings
import logging


class PIIFilter:
    """
    Pan-European PII anonymizer with:
      • High-recall address detection (pan-Europe) + apartment/unit tails (multilingual, incl. AT/DK/Nordics)
      • Postal code/city injection (pan-Europe) → LOCATION
      • Country-specific ID and TAX pattern injection (format-level)
      • Credit cards (Luhn), bank accounts (IBAN mod-97, BIC), labeled account numbers/tokens/crypto
      • Extended PERSON CLEANUP (hybrid — broad EU coverage, high precision)
      • Multilingual overlaps/filters (LOCATION near passport/ID/tax labels)
      • Added IDs/Financial/Health/Education-Employment/Comms/Device/Location entities (see ALLOWED_ENTITIES)
      • Toggleable false-positive guards for ADDRESS
    """

    PRIORITY = {
        "ADDRESS": 8,
        "PASSPORT": 7,
        "ID_NUMBER": 7,
        "DRIVER_LICENSE": 7,
        "VOTER_ID": 7,
        "RESIDENCE_PERMIT": 7,
        "BENEFIT_ID": 7,
        "MILITARY_ID": 7,

        "TAX_ID": 7,
        "CREDIT_CARD": 7,
        "BANK_ACCOUNT": 7,
        "ROUTING_NUMBER": 7,
        "ACCOUNT_NUMBER": 6,
        "PAYMENT_TOKEN": 6,
        "CRYPTO_ADDRESS": 6,

        "HEALTH_ID": 7,
        "MRN": 6,
        "INSURANCE_ID": 6,
        "HEALTH_INFO": 5,

        "STUDENT_NUMBER": 5,
        "EMPLOYEE_ID": 6,
        "PRO_LICENSE": 6,

        "IP_ADDRESS": 5,
        "DATE": 5,
        "PHONE_NUMBER": 4,
        "FAX_NUMBER": 4,

        "EMAIL_ADDRESS": 3,
        "PERSON": 2,
        "LOCATION": 1,

        "SOCIAL_HANDLE": 4,
        "MESSAGING_ID": 4,
        "MEETING_ID": 4,

        "MAC_ADDRESS": 6,
        "IMEI": 6,
        "ADVERTISING_ID": 6,
        "DEVICE_ID": 5,

        "GEO_COORDINATES": 5,
        "PLUS_CODE": 4,
        "W3W": 4,
        "LICENSE_PLATE": 5,
    }

    NATURAL_SUFFIXES = ("berg", "tal", "thal", "wald", "feld", "see", "bach")
    ADDRESS_CONTEXT_KEYWORDS = (
        "wohne", "wohnhaft", "adresse", "liegt", "befindet", "ist in", "bei",
        "live", "lives", "living", "address", "located", "on",
        "habite", "situé", "située", "se trouve",
        "vivo", "vive", "dirección", "ubicado", "ubicada", "domicilio",
        "abito", "indirizzo", "si trova", "residente",
        "moro", "endereço", "localizado", "localizada", "morada",
        "woon", "adres", "liegt", "woonachtig",
        "bor", "adress", "adresse", "ligger",
        "živim", "живу", "адрес", "na adrese", "nachází", "znajduje się", "zamieszkały", "zamieszkała", "adres",
        "διεύθυνση", "μένω", "βρίσκεται",
        "adres", "ikamet",
        "العنوان", "يسكن", "يقيم", "يقع",
    )

    ALLOWED_ENTITIES = [
        "PERSON", "EMAIL_ADDRESS", "PHONE_NUMBER", "FAX_NUMBER", "ADDRESS", "LOCATION",
        "DATE", "PASSPORT", "ID_NUMBER", "TAX_ID", "IP_ADDRESS",
        "CREDIT_CARD", "BANK_ACCOUNT", "ROUTING_NUMBER", "ACCOUNT_NUMBER", "PAYMENT_TOKEN", "CRYPTO_ADDRESS",
        "DRIVER_LICENSE", "VOTER_ID", "RESIDENCE_PERMIT", "BENEFIT_ID", "MILITARY_ID",
        "HEALTH_ID", "MRN", "INSURANCE_ID", "HEALTH_INFO",
        "STUDENT_NUMBER", "EMPLOYEE_ID", "PRO_LICENSE",
        "SOCIAL_HANDLE", "MESSAGING_ID", "MEETING_ID",
        "MAC_ADDRESS", "IMEI", "ADVERTISING_ID", "DEVICE_ID",
        "GEO_COORDINATES", "PLUS_CODE", "W3W", "LICENSE_PLATE",
    ]

    def __init__(self):
        warnings.filterwarnings("ignore")
        logging.getLogger().setLevel(logging.ERROR)

        # Feature flag to include loose unlabeled TAX fallbacks (default off)
        self.ENABLE_LOOSE_TAX = False

        self._build_patterns()
        self._setup_analyzer()

    # ===========================
    # Build all regex components
    # ===========================
    def _build_patterns(self):
        self.NAME_WORD = (
            r"(?:[A-Za-zÀ-ÖØ-öø-ÿĀ-ſ\u00C0-\u024F\u0370-\u03FF"
            r"\u0400-\u04FF\u0590-\u05FF\u0600-\u06FF\u0750-\u077F"
            r"\u08A0-\u08FF]"
            r"[A-Za-z0-9À-ÖØ-öø-ÿĀ-ſ\u00C0-\u024F\u0370-\u03FF"
            r"\u0400-\u04FF\u0590-\u05FF\u0600-\u06FF\u0750-\u077F"
            r"\u08A0-\u08FF'’\.-]*)"
        )
        self.HOUSE_NO_LABEL = r"(?:No\.?|Nr\.?|Nº|nº|N°|n°|№)"
        self.PAREN_DISTRICT = (
            r"(?:\s*\(\s*(?:[A-Z0-9ÄÖÜ][\wÀ-ÖØ-öø-ÿÄÖÜäöüß'’\.-]*"
            r"(?:[-\s][\wÀ-ÖØ-öø-ÿÄÖÜäöüß'’\.-]*)*)\s*\))?"
        )

        self.STREET_TYPES = (
            r"(?:"
            r"street|st\.?|road|rd\.?|avenue|ave\.?|boulevard|blvd\.?|lane|ln\.?|drive|dr\.?|place|square|court|ct\.?|crescent|terrace|quay|wharf|row|close|grove|parkway|pkwy|mews"
            r"|rue|chemin|che\.?|all(?:ée|ee)|impasse|imp\.?|quai|cours|passage|place|pont|square|bd\.?|boulevard|av\.?"
            r"|calle|cl\.?|carrera|cra\.?|camino|cno\.?|avenida|av\.?|paseo|pso\.?|pg\.?|plaza|pl\.?|diagonal|transversal|trv\.?|costanera|carretera|ctra\.?"
            r"|rua|r\.?|avenida|av\.?|alameda|al\.?|travessa|trv\.?|largo|lg\.?|praça|pç\.?|rodovia|rod\.?|estrada|est\.?|marginal|via|campo|bairro"
            r"|via|viale|v\.?le|vicolo|vico|piazza|p\.?za|largo|corso|strada|str\.?|contrada|c\.?da|lungotevere|lungarno|frazione|fraz\.?"
            r"|straat|laan|weg|plein|gracht|kade|dijk|brug|steeg|hof|pad"
            r"|gata|gatan|väg|vägen|allé|alle|allen|torg|torget|vej|vejen|gade|gaden|vei|veien|plass|katu|tie|kuja|polku|ranta|silta|bane|bro|veg|gate|stien"
            r"|ulica|ul\.?|aleja|al\.?|plac|pl\.?|ronda"
            r"|ulice|ul\.?|náměstí|nám\.?|třída|tř\.?|cesta"
            r"|námestie|nám\.?|trieda|tr\.?"
            r"|utca|u\.?|út|körút|krt\.?|tér"
            r"|strada|str\.?|bulevard|bd\.?|șoseaua|șos\.?|soseaua|sos\.?|calea|piața|p-ța|aleea|splaiul"
            r"|οδός|οδ\.?|λεωφόρος|λεωφ\.?|πλατεία|πλ\.?|παραλιακή"
            r"|cesta|ulica|trg|avenija|av\.?|pot|obala|nabrežje|nabrezje|most"
            r"|put|obal(?:a)?|bulevar|bulev(?:ar)?|aleja|sokak|rruga|rrugica|bulevardi|sheshi"
            r"|gatv(?:ė|e)|g\.?|prospektas|pr\.?|alėja|al\.?|aikšt(?:ė|e)|kelias"
            r"|iela|prospekts|bulvāris|laukums|krastmala"
            r"|tänav|tn\.?|puiestee|pst\.?|allee|väljak|tee|maantee|mnt\.?"
            r"|allee|weg|platz|ufer|ring|damm|straße|strasse|str\.?|gasse|gässchen|gäßchen|gässle|gäßle|gaesschen|gaessle|chaussee|chaus\.|brücke|bruecke|steig|stiege|stieg|steg|zeile|pfad|twiete|tweute|twete|hohl|hohle|berg|tal|thal|wald|feld|see|bach|kai|kanal|deich|wall|gürtel|guertel|markt|anger"
            r"|caddesi|cad\.?|sokak|sk\.?|mahallesi|mh\.?|شارع|طريق|جادة|حارة|زقاق|ميدان|جسر"
            r")"
        )

        self.STREET_SUFFIX_COMPOUND = (
            r"(?:"
            r"straße|strasse|str\.?|gasse|gässchen|gäßchen|gässle|gäßle|gaesschen|gaessle|weg|platz|ufer|ring|damm|brücke|bruecke|steig|stiege|stieg|steg|zeile|pfad|twiete|tweute|twete|hohle|hohl|berg|thal|tal|wald|feld|see|bach|gürtel|guertel|kai|kanal|deich|wall|markt|anger"
            r"|straat|laan|weg|plein|gracht|kade|dijk|brug|steeg|hof|pad"
            r"|gata|gatan|väg|vägen|allé|alle|allen|torg|torget|vej|vejen|gade|gaden|vei|veien|plass|katu|tie|kuja|polku|ranta|silta|gate|veg|stien"
            r"|utca|u\.?|út|körút|krt\.?|tér"
            r"|gatv(?:ė|e)|prospektas|alėja|aikšt(?:ė|e)|iela|bulvāris|laukums|krastmala|tänav|puiestee|väljak|tee|maantee"
            r"|cesta|ulica|trg|avenija|pot|obala|nabrežje|nabrezje|put|bulevar|aleja"
            r")"
        )

        self.FLOOR_LABEL = (
            r"(?:floor|fl\.?|flr\.?|étage|etage|etg\.?|stock|stg\.?|stiege|"
            r"og|eg|ug|piso|piano|andar|sal|verdieping|våning|vån\.?|plan|"
            r"etasje|kerros|όροφος|этаж|etaj|tr|trp)"
        )
        self.UNIT_LABEL = (
            r"(?:"
            r"apt|apt\.|apartment|unit|un\.|suite|ste\.?|flat|room|rm\.?|\#"
            r"|whg\.?|wohnung|app\.?|appartement|zi\.?|zimmer|etage|stock|"
            r"stg\.?|stiege|top"
            r"|app\.?|appt\.?|appartement|étage|etage"
            r"|depto|dpto|dep\.?|departamento|piso|pta\.?|puerta"
            r"|app\.?|appartamento|interno|int\.?|piano|scala|sc\.?"
            r"|ap\.?|apto|apartamento|andar|sala|bloco|bl\.?"
            r"|appartement|appt\.?|verdieping|bus"
            r"|lgh|lägenhet|leil\.?|leilighet|sal|etg|as\.?|asunto|vån\.?|"
            r"våning|plan|kerros|tr\.?|trp\.?|h"
            r"|byt|stan|sprat|apartman"
            r"|διαμ\.?|διαμέρισμα|όροφος"
            r"|кв\.?|квартира|эт\.?|этаж|подъезд|под\.?"
            r"|شقة|شقه|طابق|مدخل"
            r"|blk\.?|block|bloco|bldg|bld\.?"
            r"|th\.?|tv\.?|mf\.?"
            r")"
        )
        self.ORDINAL = r"(?:\d{1,2}(?:\.\s*|[º°ª]|(?:st|nd|rd|th|e|er|re)))"
        self.UNIT_VALUE = r"(?:[\w\-_/\.]{1,15})"
        self.HASH_TAIL = r"(?:\#\s*[\w\-]{1,10})"

        self.AT_TOP = r"(?:top)\s*\d[\w\-]{0,4}"
        self.AT_STIEGE = r"(?:stiege|stg\.?)\s*\d[\w\-]{0,4}"
        self.DK_DOOR = r"(?:\d{1,2}\.\s*(?:th\.?|tv\.?|mf\.?))"
        self.SE_TR = r"(?:\d{1,2}\s*(?:tr|trp)\.?)"
        self.FI_STAIR = r"(?:[A-Z]\-?\s*\d{1,4})"

        # Avoid multiline bleed by forbidding \n in glue spaces via [ \t]+ where applicable
        glue = r"[ \t]+"

        self.UNIT_TAIL = rf"""
        (?:
            {glue}?(?:,|;|/|-\s*|—\s*|،\s*)?{glue}?
            (?:
                {self.AT_TOP}
                |
                {self.AT_STIEGE}
                |
                {self.DK_DOOR}
                |
                {self.SE_TR}
                |
                {self.FI_STAIR}
                |
                (?:{self.UNIT_LABEL})\s*[:#\-]?\s*(?:{self.UNIT_VALUE})
                |
                (?:{self.HASH_TAIL})
                |
                (?:{self.ORDINAL})\s*(?:{self.FLOOR_LABEL})
                |
                (?:{self.FLOOR_LABEL})\s*(?:{self.ORDINAL})
            )
        ){{0,3}}
        """

        # Strict address patterns (replace \s+ with glue where it connects major tokens)
        self.PATTERN_NUM_TYPE_NAME = rf"""
        \b
        \d{{1,5}}\w?
        {glue}
        (?:{self.STREET_TYPES})
        {glue}
        (?:{self.NAME_WORD}(?:{glue}{self.NAME_WORD}){{0,4}})
        {self.PAREN_DISTRICT}
        {self.UNIT_TAIL}
        \b
        """

        self.PATTERN_TYPE_NAME_NUM = rf"""
        \b
        (?:{self.STREET_TYPES})
        {glue}
        (?:{self.NAME_WORD}(?:{glue}{self.NAME_WORD}){{0,4}})
        (?:{glue}?,{glue}?{self.HOUSE_NO_LABEL}\s*[:\-]?\s*)?
        {glue}
        \d{{1,5}}[A-Za-z]?
        (?:\s*[-–]\s*\d+[A-Za-z]?)?
        {self.PAREN_DISTRICT}
        {self.UNIT_TAIL}
        \b
        """

        self.PATTERN_NUM_NAME_TYPE = rf"""
        \b
        \d{{1,5}}[A-Za-z]?
        {glue}
        (?:{self.NAME_WORD}(?:{glue}{self.NAME_WORD}){{0,4}})
        {glue}
        (?:{self.STREET_TYPES})
        {self.PAREN_DISTRICT}
        {self.UNIT_TAIL}
        \b
        """

        self.PATTERN_TYPE_NAME_COMMA_NUM = rf"""
        \b
        (?:{self.STREET_TYPES})
        {glue}
        (?:{self.NAME_WORD}(?:{glue}{self.NAME_WORD}){{0,4}})
        \s*,\s*
        \d{{1,5}}[A-Za-z]?
        (?:\s*[-–]\s*\d+[A-Za-z]?)?
        {self.PAREN_DISTRICT}
        {self.UNIT_TAIL}
        \b
        """

        self.PATTERN_TYPE_NAME_LABEL_NUM = rf"""
        \b
        (?:{self.STREET_TYPES})
        {glue}
        (?:{self.NAME_WORD}(?:{glue}{self.NAME_WORD}){{0,4}})
        (?:{glue}|{glue}?,{glue}?)
        {self.HOUSE_NO_LABEL}
        \s*[:\-]?\s*
        \d{{1,5}}[A-Za-z]?
        (?:\s*[-–]\s*\d+[A-Za-z]?)?
        {self.PAREN_DISTRICT}
        {self.UNIT_TAIL}
        \b
        """

        self.PATTERN_LABEL_NUM_TYPE_NAME = rf"""
        \b
        {self.HOUSE_NO_LABEL}
        \s*[:\-]?\s*
        \d{{1,5}}[A-Za-z]?
        (?:\s*[-–]\s*\d+[A-Za-z]?)?
        {glue}
        (?:{self.STREET_TYPES})
        {glue}
        (?:{self.NAME_WORD}(?:{glue}{self.NAME_WORD}){{0,4}})
        {self.PAREN_DISTRICT}
        {self.UNIT_TAIL}
        \b
        """

        self.PATTERN_DE_SUFFIX_NUM = rf"""
        \b
        [A-ZÄÖÜ][\wÄÖÜäöüß'’-]*?(?:straße|strasse|str\.)
        \s*
        \d{{1,5}}[A-Za-z]?
        (?:\s*[-–]\s*\d+[A-Za-z]?)?
        {self.PAREN_DISTRICT}
        {self.UNIT_TAIL}
        \b
        """

        self.PATTERN_DE_PREFIX_STREET = rf"""
        \b
        (?:Am|Im|In(?:\s+der|\s+den|\s+dem)?|An(?:\s+der|\s+den|\s+dem)?|
           Auf(?:\s+der|\s+dem)?|Unter(?:\s+der|\s+den|\s+dem)?|Über(?:\s+der|\s+den|\s+dem)?|
           Vor(?:\s+der|\s+den|\s+dem)?|Hinter(?:\s+der|\s+den|\s+dem)?|Neben(?:\s+der|\s+den|\s+dem)?|
           Bei(?:\s+der|\s+den|\s+dem)?|Zu(?:m|r))
        {glue}
        (?:{self.NAME_WORD}(?:{glue}{self.NAME_WORD}){{0,4}})
        (?:{glue}\d{{1,5}}[A-Za-z]?)?
        {self.PAREN_DISTRICT}
        {self.UNIT_TAIL}
        \b
        """

        self.PATTERN_ANY_COMPOUND_SUFFIX = rf"""
        \b
        [A-ZÀ-ÖØ-ÝÄÖÜ][\wÀ-ÖØ-öø-ÿÄÖÜäöüß'’-]*?(?:{self.STREET_SUFFIX_COMPOUND})
        \s*
        \d{{0,5}}[A-Za-z]?
        (?:\s*[-–]\s*\d+[A-Za-z]?)?
        {self.PAREN_DISTRICT}
        {self.UNIT_TAIL}
        \b
        """

        self.PATTERN_ARABIC = rf"""
        \b
        (?:شارع|طريق|جادة|حي|حارة|زقاق|ميدان|جسر)
        \s+
        [^\s،,]+(?:\s+[^\s،,]+){{0,4}}
        (?:\s+(?:رقم|{self.HOUSE_NO_LABEL})\s*[:\-]?\s*\d{{1,5}}[A-Za-z]?)?
        {self.UNIT_TAIL}
        \b
        """

        self.PATTERN_CYRILLIC = rf"""
        \b
        (?:улица|ул\.?|проспект|пр-т|просп\.?|шоссе|площадь|пл\.?|бульвар|бул\.?|набережная|наб\.?|переулок|пер\.?|проезд|дорога|тракт|квартал|кв-л|микрорайон|мкр\.?)
        \s+
        [А-ЯЁ][\wА-Яа-яЁё'’\.-]*(?:\s+[А-ЯЁ][\wА-Яа-яЁё'’\.-]*){{0,4}}
        (?:\s*,\s*{self.HOUSE_NO_LABEL}\s*[:\-]?\s*)?
        \s+
        \d{{1,5}}[А-ЯA-Za-z]?
        (?:\s*[-–]\s*\d+[А-ЯA-Za-z]?)?
        {self.UNIT_TAIL}
        \b
        """

        self.PATTERN_TR_NO = rf"""
        \b
        {self.NAME_WORD}
        \s+
        (?:caddesi|cad\.?|sokak|sk\.?|mahallesi|mh\.?)
        \s*
        (?:No|Nr)\.?\s*[:\-]?\s*\d{{1,5}}[A-Za-z]?
        {self.UNIT_TAIL}
        \b
        """

        self.STRICT_ADDRESS_REGEX = (
            f"(?:{self.PATTERN_NUM_TYPE_NAME})|"
            f"(?:{self.PATTERN_TYPE_NAME_NUM})|"
            f"(?:{self.PATTERN_NUM_NAME_TYPE})|"
            f"(?:{self.PATTERN_TYPE_NAME_COMMA_NUM})|"
            f"(?:{self.PATTERN_TYPE_NAME_LABEL_NUM})|"
            f"(?:{self.PATTERN_LABEL_NUM_TYPE_NAME})|"
            f"(?:{self.PATTERN_DE_SUFFIX_NUM})|"
            f"(?:{self.PATTERN_DE_PREFIX_STREET})|"
            f"(?:{self.PATTERN_ANY_COMPOUND_SUFFIX})|"
            f"(?:{self.PATTERN_TR_NO})|"
            f"(?:{self.PATTERN_CYRILLIC})|"
            f"(?:{self.PATTERN_ARABIC})"
        )
        self.STRICT_ADDRESS_RX = re.compile(self.STRICT_ADDRESS_REGEX, re.I | re.UNICODE | re.VERBOSE)

        # POSTAL codes + City
        self.CITY_TOKEN = r"[A-ZÀ-ÖØ-ÝÄÖÜ][A-Za-zÀ-ÖØ-öø-ÿĀ-ſ\u00C0-\u024F\u0370-\u03FF\u0400-\u04FFÄÖÜäöüß'’\.]+"
        self.CITY_OR_DISTRICT = rf"{self.CITY_TOKEN}(?:[-\s]{self.CITY_TOKEN})*"

        self.POSTAL_EU_PATTERNS = [
            rf"\b(?:DE|D)?\s*[-–]?\s*(\d{{5}})\s+{self.CITY_OR_DISTRICT}{self.PAREN_DISTRICT}\b",
            rf"\b(?:AT|A)?\s*[-–]?\s*(\d{{4}})\s+{self.CITY_OR_DISTRICT}{self.PAREN_DISTRICT}\b",
            rf"\b(?:CH)?\s*[-–]?\s*(\d{{4}})\s+{self.CITY_OR_DISTRICT}{self.PAREN_DISTRICT}\b",
            rf"\b(?:LI)?\s*[-–]?\s*(\d{{4}})\s+{self.CITY_OR_DISTRICT}{self.PAREN_DISTRICT}\b",
            rf"\b(?:NL)?\s*[-–]?\s*(\d{{4}}\s?[A-Z]{{2}})\s+{self.CITY_OR_DISTRICT}{self.PAREN_DISTRICT}\b",
            rf"\b(?:BE)?\s*[-–]?\s*(\d{{4}})\s+{self.CITY_OR_DISTRICT}{self.PAREN_DISTRICT}\b",
            rf"\b(?:LU|L)?\s*[-–]?\s*(\d{{4}})\s+{self.CITY_OR_DISTRICT}{self.PAREN_DISTRICT}\b",
            rf"\b(?:DK)?\s*[-–]?\s*(\d{{4}})\s+{self.CITY_OR_DISTRICT}{self.PAREN_DISTRICT}\b",
            rf"\b(?:SE)?\s*[-–]?\s*(\d{{3}}\s?\d{{2}})\s+{self.CITY_OR_DISTRICT}{self.PAREN_DISTRICT}\b",
            rf"\b(?:NO)?\s*[-–]?\s*(\d{{4}})\s+{self.CITY_OR_DISTRICT}{self.PAREN_DISTRICT}\b",
            rf"\b(?:FI)?\s*[-–]?\s*(\d{{5}})\s+{self.CITY_OR_DISTRICT}{self.PAREN_DISTRICT}\b",
            rf"\b(?:IS)?\s*[-–]?\s*(\d{{3}})\s+{self.CITY_OR_DISTRICT}{self.PAREN_DISTRICT}\b",
            rf"\b(?:FO)?\s*[-–]?\s*(\d{{3}})\s+{self.CITY_OR_DISTRICT}{self.PAREN_DISTRICT}\b",
            r"(?i)\b((?:GIR\s?0AA)|(?:[A-HK-Y]?\d{1,2}|[A-HK-Y]\d[A-HJKPSTUW]|[A-HK-Y]\d{1,2}[A-HJKPSTUW]|[0-9][A-HJKPSTUW])\s?\d[ABD-HJLNP-UW-Z]{2}|(?:IM|JE|GY)\d[\dA-Z]?\s?\d[ABD-HJLNP-UW-Z]{2}|BFPO\s?\d{1,4}|(?:ASCN|STHL|TDCU|BBND|BIQQ|FIQQ|GX11)\s?1AA)\b",
            r"(?i)\b([AC-FHKNPRTV-Y]\d{2}\s?[0-9AC-HJ-NP-Z]{4})\b",
            r"(?i)\b(GX11\s?1AA)\b",
            rf"\b(?:FR)?\s*[-–]?\s*(\d{{5}})\s+{self.CITY_OR_DISTRICT}{self.PAREN_DISTRICT}\b",
            rf"\b(?:MC)?\s*[-–]?\s*(980\d{{2}})\s+{self.CITY_OR_DISTRICT}{self.PAREN_DISTRICT}\b",
            rf"\b(?:ES)?\s*[-–]?\s*(\d{{5}})\s+{self.CITY_OR_DISTRICT}{self.PAREN_DISTRICT}\b",
            rf"\b(?:PT)?\s*[-–]?\s*(\d{{4}}-\d{{3}})\s+{self.CITY_OR_DISTRICT}{self.PAREN_DISTRICT}\b",
            rf"\b(?:IT)?\s*[-–]?\s*(\d{{5}})\s+{self.CITY_OR_DISTRICT}{self.PAREN_DISTRICT}\b",
            rf"\b(?:SM)?\s*[-–]?\s*(4789\d)\s+{self.CITY_OR_DISTRICT}{self.PAREN_DISTRICT}\b",
            rf"\b(?:VA)?\s*[-–]?\s*(00120)\s+{self.CITY_OR_DISTRICT}{self.PAREN_DISTRICT}\b",
            r"\b(AD\d{3})\b",
            r"(?i)\b([A-Z]{3}\s?\d{2,4})\b",
            rf"\b(?:HR)?\s*[-–]?\s*(\d{{5}})\s+{self.CITY_OR_DISTRICT}{self.PAREN_DISTRICT}\b",
            rf"\b(?:SI)?\s*[-–]?\s*(\d{{4}})\s+{self.CITY_OR_DISTRICT}{self.PAREN_DISTRICT}\b",
            rf"\b(?:BA)?\s*[-–]?\s*(\d{{5}})\s+{self.CITY_OR_DISTRICT}{self.PAREN_DISTRICT}\b",
            rf"\b(?:RS)?\s*[-–]?\s*(\d{{5}})\s+{self.CITY_OR_DISTRICT}{self.PAREN_DISTRICT}\b",
            rf"\b(?:ME)?\s*[-–]?\s*(\d{{5}})\s+{self.CITY_OR_DISTRICT}{self.PAREN_DISTRICT}\b",
            rf"\b(?:MK)?\s*[-–]?\s*(\d{{4}})\s+{self.CITY_OR_DISTRICT}{self.PAREN_DISTRICT}\b",
            rf"\b(?:AL)?\s*[-–]?\s*(\d{{4}})\s+{self.CITY_OR_DISTRICT}{self.PAREN_DISTRICT}\b",
            rf"\b(?:GR)?\s*[-–]?\s*(\d{{3}}\s?\d{{2}})\s+{self.CITY_OR_DISTRICT}{self.PAREN_DISTRICT}\b",
            rf"\b(?:CY)?\s*[-–]?\s*(\d{{4}})\s+{self.CITY_OR_DISTRICT}{self.PAREN_DISTRICT}\b",
            rf"\b(?:PL)?\s*[-–]?\s*(\d{{2}}-\d{{3}})\s+{self.CITY_OR_DISTRICT}{self.PAREN_DISTRICT}\b",
            rf"\b(?:CZ)?\s*[-–]?\s*(\d{{3}}\s?\d{{2}})\s+{self.CITY_OR_DISTRICT}{self.PAREN_DISTRICT}\b",
            rf"\b(?:SK)?\s*[-–]?\s*(\d{{3}}\s?\d{{2}})\s+{self.CITY_OR_DISTRICT}{self.PAREN_DISTRICT}\b",
            rf"\b(?:HU|H)?\s*[-–]?\s*(\d{{4}})\s+{self.CITY_OR_DISTRICT}{self.PAREN_DISTRICT}\b",
            rf"\b(?:RO)?\s*[-–]?\s*(\d{{6}})\s+{self.CITY_OR_DISTRICT}{self.PAREN_DISTRICT}\b",
            rf"\b(?:BG)?\s*[-–]?\s*(\d{{4}})\s+{self.CITY_OR_DISTRICT}{self.PAREN_DISTRICT}\b",
            rf"\b(?:EE)?\s*[-–]?\s*(\d{{5}})\s+{self.CITY_OR_DISTRICT}{self.PAREN_DISTRICT}\b",
            rf"\b(?:LV)?\s*[-–]?\s*(\d{{4}})\s+{self.CITY_OR_DISTRICT}{self.PAREN_DISTRICT}\b",
            rf"\b(?:LT)?\s*[-–]?\s*(\d{{5}})\s+{self.CITY_OR_DISTRICT}{self.PAREN_DISTRICT}\b",
            rf"\b(?:UA)?\s*[-–]?\s*(\d{{5}})\s+{self.CITY_OR_DISTRICT}{self.PAREN_DISTRICT}\b",
            rf"\b(?:BY)?\s*[-–]?\s*(\d{{6}})\s+{self.CITY_OR_DISTRICT}{self.PAREN_DISTRICT}\b",
            rf"\b(?:MD)?\s*[-–]?\s*(?:MD-)?(\d{{4}})\s+{self.CITY_OR_DISTRICT}{self.PAREN_DISTRICT}\b",
            rf"\b(?:TR)?\s*[-–]?\s*(\d{{5}})\s+{self.CITY_OR_DISTRICT}{self.PAREN_DISTRICT}\b",
        ]

        # Phone (precompiled; no inline flags)
        self.PHONE_REGEX = r"""
        (?<!\w)
        (?:\+?\d{1,3}[ \-]?)?
        (?:\(?\d{1,4}\)?[ \-]?)?
        (?:\d[ \-]?){6,12}\d
        (?!\w)
        """
        self.PHONE_RX = re.compile(self.PHONE_REGEX, re.IGNORECASE | re.UNICODE | re.VERBOSE)

        # Date
        self.DATE_REGEX_1 = r"\b\d{1,2}[.\-/]\d{1,2}[.\-/]\d{2,4}\b"
        self.DATE_REGEX_2 = r"\b\d{4}[.\-/]\d{1,2}[.\-/]\d{1,2}\b"
        self.DATE_REGEX_3 = r"\b\d{1,2}\s+[A-Za-zÄÖÜäöüßÁÉÍÓÚáéíóúñç]+\s+\d{4}\b"

        # Passports / IDs (generic)
        self.US_PASSPORT_REGEX = r"\b[A-Z][0-9]{8}\b"
        self.EU_PASSPORT_REGEX = r"\b(?=[A-Z0-9]{6,9}\b)(?=.*[A-Z])[A-Z0-9]{6,9}\b"

        # ID PATTERNS (format-level)
        self.ID_PATTERNS = [
            (r"(?i)\b(?!BG|GB|NK|TN|ZZ)([A-CEGHJ-PR-TW-Z]{2}\s*\d{2}\s*\d{2}\s*\d{2}\s*[A-D])\b", "uk_nino"),
            (r"(?i)\b(\d{7}[A-W][A-IW]?)\b", "ie_ppsn"),
            (r"\b([12]\d{12}\d{2})\b", "fr_nir"),
            (r"\b(\d{8}[A-HJ-NP-TV-Z])\b", "es_dni"),
            (r"\b([XYZ]\d{7}[A-Z])\b", "es_nie"),
            (r"\b([A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z])\b", "it_codice_fiscale"),
            (r"\b(?=[A-Z0-9]{9}\b)(?=.*[A-Z])[A-Z0-9]{9}\b", "de_personalausweis"),
            (r"\b(\d{9})\b", "nl_bsn"),
            (r"\b(\d{2}\.\d{2}\.\d{2}-\d{3}\.\d{2}|\d{6}-\d{3}\.\d{2}|\d{2}\.\d{2}\.\d{2}-\d{5}|\d{6}-\d{5})\b", "be_rn"),
            (r"\b([0-3]\d[01]\d\d{2}[- ]?\d{4})\b", "dk_cpr"),
            (r"\b((?:\d{6}|\d{8})[-+]\d{4})\b", "se_personnummer"),
            (r"\b([0-3]\d[01]\d\d{2}\d{5})\b", "no_fnr"),
            (r"\b([0-3]\d[01]\d\d{2}[A\+\-]\d{3}[0-9A-Y])\b", "fi_hetu"),
            (r"\b([0-3]\d[01]\d\d{2}-\d{4})\b", "is_kennitala"),
            (r"\b(\d{11})\b", "pl_pesel"),
            (r"\b(\d{6}/\d{3,4})\b", "czsk_birthno"),
            (r"\b([1-8]\d{12})\b", "ro_cnp"),
            (r"\b(\d{10})\b", "bg_egn"),
            (r"\b(\d{11})\b", "lt_id"),
            (r"\b([0-3]\d[01]\d\d{2}-\d{5})\b", "lv_personas_kods"),
            (r"\b(\d{11})\b", "ee_isikukood"),
            (r"\b(\d{11})\b", "hr_oib"),
            (r"\b(\d{13})\b", "si_emso"),
            (r"\b(\d{13})\b", "jmbg_like"),
            (r"\b(\d{11})\b", "gr_amka"),
            (r"\b(756(?:\.\d{4}\.\d{4}\.\d{2}|\d{10}))\b", "ch_ahv"),
        ]

        # TAX split
        self.TAX_PATTERNS_STRICT = [
            (r"\b(BE\s?\d{10})\b", "vat_be"),
            (r"\b(BG\s?\d{9,10})\b", "vat_bg"),
            (r"\b(CZ\s?\d{8,10})\b", "vat_cz"),
            (r"\b(DK\s?\d{8})\b", "vat_dk"),
            (r"\b(DE\s?\d{9})\b", "vat_de"),
            (r"\b(EE\s?\d{9})\b", "vat_ee"),
            (r"\b(IE\s?[0-9A-Z]{7,8}[A-W])\b", "vat_ie"),
            (r"\b(EL\s?\d{9}|GR\s?\d{9})\b", "vat_gr"),
            (r"\b(ES\s?[A-Z0-9]\d{7}[A-Z0-9])\b", "vat_es"),
            (r"\b(FI\s?\d{8})\b", "vat_fi"),
            (r"\b(FR\s?[0-9A-Z]{2}\d{9})\b", "vat_fr"),
            (r"\b(HR\s?\d{11})\b", "vat_hr"),
            (r"\b(HU\s?\d{8})\b", "vat_hu"),
            (r"\b(IT\s?\d{11})\b", "vat_it"),
            (r"\b(LT\s?(?:\d{9}|\d{12}))\b", "vat_lt"),
            (r"\b(LU\s?\d{8})\b", "vat_lu"),
            (r"\b(LV\s?\d{11})\b", "vat_lv"),
            (r"\b(MT\s?\d{8})\b", "vat_mt"),
            (r"\b(NL\s?\w{9}B\d{2})\b", "vat_nl"),
            (r"\b(PL\s?\d{10})\b", "vat_pl"),
            (r"\b(PT\s?\d{9})\b", "vat_pt"),
            (r"\b(RO\s?\d{2,10})\b", "vat_ro"),
            (r"\b(SK\s?\d{10})\b", "vat_sk"),
            (r"\b(SI\s?\d{8})\b", "vat_si"),
            (r"\b(SE\s?\d{10}01)\b", "vat_se"),
            (r"\b(CY\s?\d{8}[A-Z])\b", "vat_cy"),
            (r"\b(NO\s?\d{9}MVA)\b", "vat_no"),
            (r"\b(CH\s?CHE\d{9}(?:TVA|MWST|IVA)?)\b", "vat_ch"),
            (r"\b(GB\s?(?:\d{9}|\d{12}|(?:GD|HA)\d{3}))\b", "vat_gb"),
        ]
        self.TAX_PATTERNS_LOOSE = [
            (r"\b(\d{11})\b", "de_steuerid"),
            (r"\b(\d{10})\b", "uk_utr"),
            (r"\b(\d{9})\b", "fr_siren"),
            (r"\b(\d{14})\b", "fr_siret"),
            (r"\b(\d{11})\b", "it_piva"),
            (r"\b([A-Z]\d{7}[A-Z]|\d{8}[A-Z])\b", "es_nif_unlabeled"),
            (r"\b([125689]\d{8})\b", "pt_nif"),
            (r"\b(\d{9}B\d{2})\b", "nl_btw_unlabeled"),
            (r"\b(\d{10})\b", "be_enterprise"),
            (r"\b(\d{8})\b", "dk_cvr"),
            (r"\b(\d{9})\b", "no_orgnr"),
            (r"\b(\d{8})\b", "fi_ytunnus"),
            (r"\b(\d{10})\b", "pl_nip"),
            (r"\b(\d{9}|\d{14})\b", "pl_regon"),
            (r"\b(\d{10})\b", "sk_dic"),
            (r"\b(\d{8})\b", "hu_adoszam"),
            (r"\b(\d{2,10})\b", "ro_cui"),
            (r"\b(\d{9}|\d{13})\b", "bg_eik"),
            (r"\b(\d{11})\b", "hr_oib_tax"),
            (r"\b(\d{8})\b", "si_tax"),
            (r"\b(\d{9,12})\b", "lt_lv_ee_tax"),
            (r"\b(\d{9})\b", "gr_afm"),
            (r"\b(\d{8}[A-Z])\b", "cy_tax"),
            (r"\b(\d{8})\b", "mt_vat_unlabeled"),
            (r"\b(\d{8})\b", "lu_vat_unlabeled"),
        ]

        # Label-based ID/TAX capture
        self.LABELED_ID_VALUE_RX = re.compile(
            r"(?i)\b(?:personalausweis(?:nummer|nr\.?)|identity\s*card|id\s*(?:no\.?|number)|dni|nif|nie|bsn|pesel|egn|cnp|amka|cpr|rodné\s*číslo|rodne\s*cislo|jmbg|emšo|emso)"
            r"\s*[:#]?\s*([A-Z0-9][A-Z0-9\-]{4,24})"
        )
        self.LABELED_TAX_VALUE_RX = re.compile(
            r"(?i)\b(?:steuer[-\s]*id|steueridentifikationsnummer|tin|tax\s*id|tax\s*number|vat|ust-?id(?:nr\.?)?|ustid|vies|nif|nie|siren|siret|piva|p\.?iva|afm|utr|cvr|oib|nip|regon|dic|cui|eik|bulstat)"
            r"\s*[:#]?\s*([A-Z]{2}\s*[A-Z0-9][A-Z0-9\.\-\s]{1,24}|[A-Z0-9\-\s]{6,24})"
        )

        # US IDs: SSN/ITIN/EIN (label-led only)
        self.SSN_LABEL_RX = re.compile(r"(?i)\bssn\b[:#\-]?\s*(\d{3}-\d{2}-\d{4}|\d{9})")
        self.ITIN_LABEL_RX = re.compile(r"(?i)\bitin\b[:#\-]?\s*(\d{3}-\d{2}-\d{4}|\d{9})")
        self.EIN_LABEL_RX = re.compile(r"(?i)\bein\b[:#\-]?\s*(\d{2}-\d{7})")

        # IP regexes
        self.IPV4_REGEX = r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d?\d)\b"
        ipv6_core = (
            r"(?:"
            r"(?:[A-F0-9]{1,4}:){7}[A-F0-9]{1,4}|"
            r"(?:[A-F0-9]{1,4}:){1,7}:|"
            r":(?::[A-F0-9]{1,4}){1,7}|"
            r"(?:[A-F0-9]{1,4}:){1,6}:[A-F0-9]{1,4}|"
            r"(?:[A-F0-9]{1,4}:){1,5}(?::[A-F0-9]{1,4}){1,2}|"
            r"(?:[A-F0-9]{1,4}:){1,4}(?::[A-F0-9]{1,4}){1,3}|"
            r"(?:[A-F0-9]{1,4}:){1,3}(?::[A-F0-9]{1,4}){1,4}|"
            r"(?:[A-F0-9]{1,4}:){1,2}(?::[A-F0-9]{1,4}){1,5}|"
            r"[A-F0-9]{1,4}:(?::[A-F0-9]{1,4}){1,6}|"
            r"::(?:[A-F0-9]{1,4}:){0,6}[A-F0-9]{1,4}"
            r")"
        )
        self.IPV6_REGEX = r"(?i)(?<![A-F0-9:])" + ipv6_core + r"(?![A-F0-9:])"

        # PERSON intros (limit to max 2 tokens capture)
        intro_map = {
            "en": [r"\bmy name is\s+"],
            "de": [r"\bmein name ist\s+", r"\bich hei(?:ß|ss)e\s+"],
            "fr": [r"\bje m(?:'|’| )appelle\s+", r"\bmon nom est\s+"],
            "es": [r"\bme llamo\s+", r"\bmi nombre es\s+"],
            "it": [r"\bmi chiamo\s+", r"\bil mio nome è\s+"],
            "pt": [r"\bmeu nome é\s+", r"\bo meu nome é\s+", r"\bchamo-me\s+"],
            "nl": [r"\bik heet\s+", r"\bmijn naam is\s+"],
            "sv": [r"\bjag heter\s+"],
            "no": [r"\bjeg heter\s+"],
            "da": [r"\bjeg hedder\s+"],
            "fi": [r"\bminun nimeni on\s+", r"\bnimeni on\s+"],
            "is": [r"\bég heiti\s+"],
            "pl": [r"\bnazywam si(?:ę|e)\s+"],
            "cs": [r"\bjmenuji se\s+"],
            "sk": [r"\bvol[aá]m sa\s+", r"\bvolám sa\s+"],
            "hu": [r"\ba nevem\s+", r"\bh(?:í|i)vnak\s+"],
            "ro": [r"\bnumele meu este\s+", r"\bm[ăa]\s+numesc\s+"],
            "bg": [r"\bказвам се\s+"],
            "el": [r"\bμε λένε\s+", r"\bονομάζομαι\s+"],
            "sq": [r"\bquhem\s+"],
            "sl": [r"\bime mi je\s+"],
            "hr": [r"\bzovem se\s+"],
            "bs": [r"\bzovem se\s+"],
            "sr": [r"\bzovem se\s+"],
            "lt": [r"\bmano vardas(?: yra)?\s+"],
            "lv": [r"\bmani sauc\s+"],
            "et": [r"\bminu nimi on\s+"],
            "mt": [r"\bjisimni\s+"],
            "ga": [r"\bis é mo ainm\s+"],
            "ru": [r"\bменя зовут\s+"],
            "uk": [r"\bмене звати\s+", r"\bмене звуть\s+"],
            "be": [r"\bмяне завуць\s+"],
            "tr": [r"\bbenim ad[ıi]m\s+"],
            "ar": [r"(?:^|\b)(?:اسمي|انا اسمي|أنا اسمي)\s+"],
        }
        self.INTRO_PATTERNS = []
        for starters in intro_map.values():
            for s in starters:
                pat = re.compile(s + r"([^\s,;:.]+(?:\s+[^\s,;:.]+){0,1})", re.IGNORECASE | re.UNICODE)
                self.INTRO_PATTERNS.append(pat)

        # PERSON negative lexicon / single-token blockers (extended)
        self.NON_PERSON_SINGLE_TOKENS = {
            "meine","mein","meiner"," ist","und","y","mi","il","la","el","le","les","de","des","del","da",
            "sono","soy","ich","bin","am","i","je","j'","j’","yo","tu","vos","vous","nous","vous",
            "abito","vivo","habito","wohne","adresse","indirizzo","dirección","direccion","direccio",
            "numero","nummer","numéro","telefono","telefon","tel","telefono","telefón","telefonnummer",
            "my","name","is","live","lives","address",
            "ik","ben","mijn","naam","is","heet","adres","woon",
            "jeg","jag","bor","hedder","heter","adress","adresse",
            "meu","minha","nome","é","se","chiama","chiamo","llamo","nombre","soy","estoy",
            "ja","já","jestem","nazywam","jmenuji","volám","volam","se","adres","адрес","имя","меня","зовут",
            "zovem","ime","je","sam",
            "είμαι","με","λένε","ονομάζομαι",
            "via","viale","vico","vicolo","piazza","corso","strada","rue","chemin","allée","impasse",
            "calle","carrera","avenida","paseo","plaza","rua","avenida","alameda","travessa","praça",
            "straat","laan","weg","plein","gracht","kade","dijk","steeg","hof","pad",
            "gata","väg","vej","gade","vei",
            "katu","tie","ulica","ulice","náměstí","třída","utca","körút","tér","strada","bulevard","șoseaua",
            "οδός","λεωφόρος","πλατεία","улица","проспект","площадь","бульвар","набережная",
            "straße","strasse","str.","gasse","weg","allee","platz","ufer","ring","damm","twiete","pfad","zeile",
            # Added blockers
            "benim","numero","nummer","numéro","email","e-mail","mail","insurance","policy","kontonummer",
            "passeport","passport","domicile","meine nummer","meine", "nummer"
        }

        self.PERSON_BLACKLIST_WORDS = {
            "personalausweisnummer","kontonummer","insurance","policy","diagnosed",
            "passeport","passport","domicile","meine nummer","bridi", "البريد", "الإلكتروني", "هاتفي", "عنواني"
        }

        self.PRONOUN_PERSONS = {
            "i","me","you","he","she","we","they",
            "ich","du","er","sie","wir","ihr","sie",
            "je","tu","il","elle","nous","vous","ils","elles",
            "yo","tú","tu","él","ella","nosotros","vosotros","ellos","elas","eu","ele","ela","nós","vocês","voi","loro","io","tu","lui","lei","noi","voi",
            "ik","jij","hij","zij","wij","jullie","zij",
            "jeg","du","han","hun","vi","dere","de","jag","du","han","hon","vi","ni","de","jeg","du","han","hun","vi","i","de",
            "minä","sinä","hän","me","te","he",
            "ja","ty","on","ona","my","wy","oni","one",
            "ja","ti","on","ona","mi","vi","oni","one",
            "eu","tu","el","ea","noi","voi","ei","ele",
            "εγώ","εσύ","αυτός","αυτή","εμείς","εσείς","αυτοί","αυτές","αυτά",
            "я","ты","он","она","мы","вы","они","я","ти","він","вона","ми","ви","вони","я","ты","ён","яна","мы","вы","яны",
        }

        # Street blockers (for PERSON plausibility)
        self.STREET_BLOCKERS = {
            "via","viale","vicolo","vico","piazza","corso","strada","rue","chemin","allée","impasse",
            "calle","carrera","avenida","paseo","plaza","rua","alameda","travessa","praça","rodovia","estrada",
            "straat","laan","weg","plein","gracht","kade","dijk","steeg","hof","pad",
            "gata","gatan","väg","vägen","allé","alle","allen","torg","vej","vejen","gade","gaden","vei","veien","plass",
            "katu","tie","kuja","polku","ranta","silta",
            "ulica","ulice","náměstí","třída","cesta","utca","körút","tér","strada","bulevard","șoseaua","splaiul","piața",
            "οδός","λεωφόρος","πλατεία",
            "улица","проспект","площадь","бульвар","набережная","переулок",
            "straße","strasse","str.","gasse","weg","allee","platz","ufer","ring","damm","twiete","pfad","zeile",
        }

        self.INTRO_REGEXES = [
            re.compile(pat, re.I | re.UNICODE) for pat in [
                r"^(?:my name is)\s+",
                r"^(?:je m(?:'|’| )appelle)\s+",
                r"^(?:mein name ist)\s+",
                r"^(?:ich hei(?:ß|ss)e)\s+",
                r"^(?:me llamo)\s+",
                r"^(?:mi chiamo)\s+",
                r"^(?:meu nome é|o meu nome é|chamo-me)\s+",
                r"^(?:ik heet|mijn naam is)\s+",
                r"^(?:jag heter)\s+",
                r"^(?:jeg heter|jeg hedder)\s+",
                r"^(?:minun nimeni on|nimeni on)\s+",
                r"^(?:ég heiti)\s+",
                r"^(?:nazywam si(?:ę|e))\s+",
                r"^(?:jmenuji se)\s+",
                r"^(?:vol[aá]m sa|volám sa)\s+",
                r"^(?:a nevem|h(?:í|i)vnak)\s+",
                r"^(?:numele meu este|m[ăa]\s+numesc)\s+",
                r"^(?:казвам се)\s+",
                r"^(?:με λένε|ονομάζομαι)\s+",
                r"^(?:quhem)\s+",
                r"^(?:ime mi je)\s+",
                r"^(?:zovem se)\s+",
                r"^(?:mano vardas(?: yra)?)\s+",
                r"^(?:mani sauc)\s+",
                r"^(?:minu nimi on)\s+",
                r"^(?:jisimni)\s+",
                r"^(?:is é mo ainm)\s+",
                r"^(?:benim ad[ıi]m)\s+",
                r"^(?:اسمي|انا اسمي|أنا اسمي)\s+",
                r"^(?:меня зовут)\s+",
                r"^(?:мене звати|мене звуть)\s+",
                r"^(?:мяне завуць)\s+",
            ]
        ]

        # Keywords for label filtering
        self.PASSPORT_KEYWORDS = tuple({
            "passport","reisepass","pass","passeport","pasaporte","passaporte","passaporto","paspoort",
            "paszport","útlevél","pașaport","паспорт","διαβατήριο","pasaport","جواز سفر","جواز",
        })
        self.ID_KEYWORDS = tuple({
            "id","identity","identity card","id card","national id",
            "personalausweis","ausweis","perso","carte d'identité","carte nationale d'identité","cni",
            "dni","documento de identidad","carnet de identidad","ine",
            "carta d'identità","carta di identità","ci",
            "cartão de cidadão","bilhete de identidade",
            "identiteitskaart","id-kaart","id kaart",
            "id-kort","identitetskort","henkilökortti",
            "dowód","dowod","dowód osobisty","dowod osobisty",
            "občanský průkaz","obcansky prukaz","občiansky preukaz","obciansky preukaz","op",
            "személyi igazolvány","szemelyi igazolvany","személyi","szemelyi",
            "carte de identitate","лична карта","ταυτότητα","удостоверение личности",
            "kimlik","kimlik kartı","tc kimlik","هوية","بطاقة هوية",
        })
        self.TAX_KEYWORDS = tuple({
            "tax id","tin","vat","vat id","vat no","vat number","vies",
            "steuer-id","steueridentifikationsnummer","steuernummer","ust-idnr","ustid","mwst",
            "numéro fiscal","numero fiscal","numéro de tva","tva","siren","siret",
            "nif","cif","iva","nie",
            "contribuinte","número de contribuinte",
            "p.iva","piva","partita iva","codice fiscale",
            "btw","btw-nummer","rsin",
            "momsnr","moms","organisationsnummer",
            "cvr","se-nummer","orgnr","mva","alv","y-tunnus",
            "nip","regon","dič","dic","ičo","ico","ič dph","ic dph",
            "adószám","adoszam","áfa","afa",
            "cui","cif","еик","bulstat","dds","ддс",
            "αφμ","φπα","инн","кпп","едрпоу","єдрпоу","vergi no","vkn","رقم ضريبي","ضريبة","ضريبة القيمة المضافة",
        })

        # IBAN/BIC
        self.IBAN_RX = re.compile(r"\b(?:[A-Z]{2}[ -]?\d{2}(?:[ -]?[A-Z0-9]){11,30})\b", re.IGNORECASE)
        self.BIC_RX = re.compile(r"\b([A-Z]{4})([A-Z]{2})([A-Z0-9]{2})([A-Z0-9]{3})?\b")
        self.ISO_COUNTRIES = {
            "AD","AE","AF","AG","AI","AL","AM","AO","AR","AT","AU","AW","AX","AZ","BA","BB","BD","BE","BF","BG","BH","BI","BJ",
            "BL","BM","BN","BO","BQ","BR","BS","BT","BV","BW","BY","BZ","CA","CC","CD","CF","CG","CH","CI","CK","CL","CM","CN",
            "CO","CR","CU","CV","CW","CX","CY","CZ","DE","DJ","DK","DM","DO","DZ","EC","EE","EG","EH","ER","ES","ET","FI","FJ",
            "FK","FM","FO","FR","GA","GB","GD","GE","GF","GG","GH","GI","GL","GM","GN","GP","GQ","GR","GS","GT","GU","GW","GY",
            "HK","HM","HN","HR","HT","HU","ID","IE","IL","IM","IN","IO","IQ","IR","IS","IT","JE","JM","JO","JP","KE","KG","KH",
            "KI","KM","KN","KP","KR","KW","KY","KZ","LA","LB","LC","LI","LK","LR","LS","LT","LU","LV","LY","MA","MC","MD","ME",
            "MF","MG","MH","MK","ML","MM","MN","MO","MP","MQ","MR","MS","MT","MU","MV","MW","MX","MY","MZ","NA","NC","NE","NF",
            "NG","NI","NL","NO","NP","NR","NU","NZ","OM","PA","PE","PF","PG","PH","PK","PL","PM","PN","PR","PS","PT","PW","PY",
            "QA","RE","RO","RS","RU","RW","SA","SB","SC","SD","SE","SG","SH","SI","SJ","SK","SL","SM","SN","SO","SR","SS","ST",
            "SV","SX","SY","SZ","TC","TD","TF","TG","TH","TJ","TK","TL","TM","TN","TO","TR","TT","TV","TW","TZ","UA","UG","UM",
            "US","UY","UZ","VA","VC","VE","VG","VI","VN","VU","WF","WS","YE","YT","ZA","ZM","ZW",
        }

        bank_labels = (
            r"(?:iban|bic|swift|account(?:\s*no\.?)?|acct|acct\.?|"
            r"konto(?:nummer)?|kontonummer|bankverbindung|rechnung|"
            r"rib|nrb|bban|cuenta|nº\s*de\s*cuenta|numero\s*de\s*cuenta|ccc|"
            r"conto|n\.\s*conto|"
            r"conta|nº\s*conta|n\.?\s*conta|"
            r"rekening|rek\.?nr|reknummer|"
            r"kontonr|kontonummer|"
            r"rachunek|nr\s*konta|"
            r"číslo\s*účtu|cislo\s*uctu|č\.\s*ú.,?|"
            r"számla(?:szám)?|szamlaszam|"
            r"cont|număr\s*cont|"
            r"сч[её]т|номер\s*сч[её]та|"
            r"λογαριασμός|αριθμός\s*λογαριασμού|"
            r"hesap\s*no|"
            r"آيبان|ايبان|رقم\s*الحساب)"
        )
        card_labels = (
            r"(?:card|card\s*no\.?|pan|cc|visa|mastercard|master\s*card|amex|american\s*express|diners|jcb|"
            r"karte|kartennummer|"
            r"carte|numéro\s*de\s*carte|"
            r"tarjeta|número\s*de\s*tarjeta|"
            r"carta|numero\s*di\s*carta|"
            r"cartão|numero\s*do\s*cartão|"
            r"kort|kortnummer|"
            r"karta|numer\s*karty|"
            r"карта|номер\s*карты|"
            r"بطاقة|رقم\s*البطاقة)"
        )
        self.LABELED_BANK_RX = re.compile(
            rf"(?i)\b{bank_labels}\s*[:#\-]?\s*([A-Z0-9][A-Z0-9 \-]{{6,64}})",
            re.UNICODE
        )
        self.LABELED_CC_RX = re.compile(
            rf"(?i)\b{card_labels}\s*[:#\-]?\s*(([0-9][0-9 \-]{{11,25}}[0-9]))",
            re.UNICODE
        )
        self.ROUTING_RX = re.compile(r"(?<!\d)(\d{9})(?!\d)")
        self.ACCT_LABEL_RX = re.compile(
            rf"(?i)\b(?:{bank_labels})\s*[:#\-]?\s*([A-Z0-9][A-Z0-9 \-]{{6,34}})",
            re.UNICODE
        )
        self.PAYMENT_TOKEN_RX = re.compile(
            r"(?i)\b(?:token|payment\s*token|client\s*secret|api\s*key|api\s*token|secret(?:\s*key)?|bearer\s*token|stripe\s*key|pk_(?:live|test)_[A-Za-z0-9]{10,}|sk_(?:live|test)_[A-Za-z0-9]{10,})\b[:=\s\-]*([A-Za-z0-9_\-]{16,128})"
        )

        self.CRYPTO_BTC_LEGACY = re.compile(r"\b[13][a-km-zA-HJ-NP-Z1-9]{25,34}\b")
        self.CRYPTO_BTC_BECH32 = re.compile(r"\b(?:bc1)[0-9a-z]{11,71}\b")
        self.CRYPTO_ETH = re.compile(r"\b0x[a-fA-F0-9]{40}\b")

        # Health patterns
        self.NHS_CAND_RX = re.compile(r"\b(?:(\d{3})\s*(\d{3})\s*(\d{4}))\b")
        self.MRN_RX = re.compile(r"(?i)\b(?:mrn|medical\s*record\s*number|numéro\s*de\s*dossier|aktenzeichen)\b[:#\-]?\s*([A-Z0-9\-]{6,18})")
        self.INSURANCE_ID_RX = re.compile(r"(?i)\b(?:insurance\s*(?:id|policy|member)\b|versicherungsnummer|policen(?:nummer)?|nº\s*poliza)\b[:#\-]?\s*([A-Z0-9\-]{6,20})")
        self.HEALTH_ID_RX = re.compile(r"(?i)\b(?:health\s*id|patient\s*id|nhs\s*number)\b[:#\-]?\s*([A-Z0-9 \-]{6,20})")
        self.HEALTH_INFO_RX = re.compile(r"(?i)\b(?:diagnos(?:is|ed)|icd\-?10|icd\-?9|hiv|cancer|diabetes|pregnan(?:t|cy)|medicat(?:ion|e)|prescription|allerg(?:y|ies)|blood\s*type)\b")

        # Education/Employment
        self.STUDENT_NUMBER_RX = re.compile(r"(?i)\b(?:student\s*(?:id|number)|matriculation|matrikel(?:nummer)?|matricula|roll\s*number)\b[:#\-]?\s*([A-Z0-9\-]{5,16})")
        self.EMPLOYEE_ID_RX = re.compile(r"(?i)\b(?:employee\s*(?:id|number)|staff\s*id|personalnummer|personnel\s*number)\b[:#\-]?\s*([A-Z0-9\-]{5,16})")
        self.PRO_LICENSE_RX = re.compile(r"(?i)\b(?:license\s*(?:no|number)|bar\s*number|medical\s*license|professional\s*license)\b[:#\-]?\s*([A-Z0-9\-]{5,20})")

        # Contact/Comms
        self.SOCIAL_HANDLE_RX = re.compile(r"(?<![\w@])@([A-Za-z0-9_]{3,32})(?![^\s@]*\.[^\s@])")
        self.DISCORD_ID_RX = re.compile(r"\b([A-Za-z0-9._\-]{2,32}#\d{4})\b")
        self.MESSAGING_LABELED_RX = re.compile(r"(?i)\b(?:telegram|skype|signal|wechat|line)\b[:#\-]?\s*([A-Za-z0-9._\-]{2,64})")
        self.ZOOM_ID_RX = re.compile(r"(?i)\b(?:meeting\s*id|zoom\s*id)\b[:#\-]?\s*([0-9][0-9 \-]{7,13}[0-9])")
        self.MEET_CODE_RX = re.compile(r"\b([a-z]{3}-[a-z]{4}-[a-z]{3,4})\b")

        self.FAX_LABEL_RX = re.compile(r"(?i)\bfax\b[:\s\-]*")

        # Devices/Network
        self.MAC_RX = re.compile(r"\b(?:[0-9A-F]{2}[:-]){5}[0-9A-F]{2}\b|\b[0-9A-F]{12}\b", re.IGNORECASE)
        self.IMEI_RX = re.compile(r"\b(?:\d[ \-]?){14}\d\b")
        self.UUID_RX = re.compile(r"\b[0-9a-fA-F]{8}\-[0-9a-fA-F]{4}\-[0-9a-fA-F]{4}\-[0-9a-fA-F]{4}\-[0-9a-fA-F]{12}\b")
        self.AD_ID_LABEL_RX = re.compile(r"(?i)\b(?:idfa|aaid|advertis(?:ing)?\s*id)\b[:#\-]?\s*(" + self.UUID_RX.pattern + r")")
        self.DEVICE_ID_LABEL_RX = re.compile(r"(?i)\b(?:device\s*id|udid)\b[:#\-]?\s*(" + self.UUID_RX.pattern + r")")

        # Location extras
        self.GEO_COORDS_RX = re.compile(r"\b([+-]?\d{1,2}\.\d+)[,\s]+([+-]?\d{1,3}\.\d+)\b")
        self.PLUS_CODE_RX = re.compile(r"\b[23456789CFGHJMPQRVWX]{2,8}\+[23456789CFGHJMPQRVWX]{2,3}\b")
        self.W3W_RX = re.compile(r"\b///([a-z]+(?:\.[a-z]+){2,})\b")
        self.PLATE_LABEL_RX = re.compile(r"(?i)\b(?:license\s*plate|registration|plate\s*no|matr[ií]cula|targa|immatriculation|kennzeichen|număr\s*de\s*înmatriculare|车牌)\b[:#\-]?\s*([A-Z0-9\- ]{4,12})")

    # ====================
    # Analyzer setup
    # ====================
    def _setup_analyzer(self):
        self.analyzer = AnalyzerEngine()
        self.anonymizer = AnonymizerEngine()

        self.address_recognizer = PatternRecognizer(
            supported_entity="ADDRESS", supported_language="all",
            patterns=[Pattern("strict_address", self.STRICT_ADDRESS_REGEX, 0.80)],
        )
        phone_compact = r"(?<!\w)(?:\+?\d{1,3}[ -]?)?(?:\(?\d{1,4}\)?[ -]?)?(?:\d[ -]?){6,12}\d(?!\w)"
        self.phone_recognizer = PatternRecognizer(
            supported_entity="PHONE_NUMBER", supported_language="all",
            patterns=[Pattern("intl_phone", phone_compact, 0.72)],
        )
        self.date_recognizer = PatternRecognizer(
            supported_entity="DATE", supported_language="all",
            patterns=[Pattern("dob_1", self.DATE_REGEX_1, 0.70),
                      Pattern("dob_2", self.DATE_REGEX_2, 0.70),
                      Pattern("dob_3", self.DATE_REGEX_3, 0.65)],
        )
        self.passport_recognizer = PatternRecognizer(
            supported_entity="PASSPORT", supported_language="all",
            patterns=[Pattern("us_passport", self.US_PASSPORT_REGEX, 0.80),
                      Pattern("eu_passport_generic", self.EU_PASSPORT_REGEX, 0.70)],
        )
        self.id_recognizer = PatternRecognizer(
            supported_entity="ID_NUMBER", supported_language="all",
            patterns=[Pattern("de_personalausweis", r"\b(?=[A-Z0-9]{9}\b)(?=.*[A-Z])[A-Z0-9]{9}\b", 0.78)],
        )
        self.ip_recognizer = PatternRecognizer(
            supported_entity="IP_ADDRESS", supported_language="all",
            patterns=[Pattern("ipv4", self.IPV4_REGEX, 0.85),
                      Pattern("ipv6", self.IPV6_REGEX, 0.85)],
        )
        self.mac_recognizer = PatternRecognizer(
            supported_entity="MAC_ADDRESS", supported_language="all",
            patterns=[Pattern("mac", self.MAC_RX.pattern, 0.60)],
        )
        self.imei_recognizer = PatternRecognizer(
            supported_entity="IMEI", supported_language="all",
            patterns=[Pattern("imei", self.IMEI_RX.pattern, 0.40)],
        )
        self.cc_recognizer = PatternRecognizer(
            supported_entity="CREDIT_CARD", supported_language="all",
            patterns=[Pattern("cc_pan", r"(?:(?<!\w)(?:\d[ -]?){13,19}\d(?!\w))", 0.40)],
        )
        self.bank_recognizer = PatternRecognizer(
            supported_entity="BANK_ACCOUNT", supported_language="all",
            patterns=[Pattern("iban", self.IBAN_RX.pattern, 0.40),
                      Pattern("bic", self.BIC_RX.pattern, 0.40)],
        )

        for rec in [
            self.address_recognizer, self.phone_recognizer, self.date_recognizer,
            self.passport_recognizer, self.id_recognizer, self.ip_recognizer,
            self.mac_recognizer, self.imei_recognizer, self.cc_recognizer, self.bank_recognizer
        ]:
            self.analyzer.registry.add_recognizer(rec)

    # ====================
    # Person helpers
    # ====================
    def _trim_intro(self, span: str):
        for rx in self.INTRO_REGEXES:
            m = rx.match(span)
            if m:
                off = m.end()
                return span[off:], off
        return span, 0

    def _plausible_person(self, span: str, text: str, start: int):
        s = span.strip()
        if not s:
            return False
        if re.search(r"\b(mail|e-mail|email|correo|e-?posta|adresse|address|telefon|phone|tel)\b", s, re.I):
            return False
        if re.search(r"\b(appelle|numero|nummer|número|policy|license|licence|kontonummer|passeport|passport)\b", s, re.I):
            return False
        if re.match(r"^\s*(?:je\s+m['’]|j['’]|je m['’])", s.lower()):
            return False

        tokens = [t for t in re.split(r"\s+", s) if t]
        low = [t.lower() for t in tokens]
        if any(tok in self.STREET_BLOCKERS for tok in low):
            return False
        if any(tok in self.NON_PERSON_SINGLE_TOKENS for tok in low):
            return False
        if len(tokens) > 1:
            if any(tok in self.PERSON_BLACKLIST_WORDS for tok in low):
                return False
            # Require at least one capitalized Latin token
            latin_tokens = [t for t in tokens if re.match(r"^[A-Za-zÀ-ÖØ-öø-ÿĀ-ſ]", t)]
            if latin_tokens and not any(t[0].isupper() for t in latin_tokens):
                return False
            return True
        t0 = low[0]
        if t0 in self.PRONOUN_PERSONS:
            return False
        prefix = text[max(0, start - 40):start].lower()
        intro_cues = [
            "my name is", "je m", "mein name", "ich hei", "me llamo", "mi chiamo",
            "meu nome", "chamo-me", "ik heet", "mijn naam", "jag heter", "jeg heter", "jeg hedder",
            "minun nimeni", "nimeni on", "ég heiti", "nazywam", "jmenuji se", "volám sa", "volam sa",
            "a nevem", "hívnak", "ma numesc", "mă numesc", "казвам се", "με λένε", "ονομάζομαι",
            "quhem", "ime mi je", "zovem se", "mano vardas", "mani sauc", "minu nimi on",
            "jisimni", "is é mo ainm", "benim adım", "اسمي", "меня зовут", "мене звати", "мене звуть", "мяне завуць",
        ]
        if any(cue in prefix for cue in intro_cues):
            return True
        if re.match(r"^[A-Za-zÀ-ÖØ-öø-ÿĀ-ſ]", tokens[0]) and not tokens[0][0].isupper():
            return False
        return True

    def _inject_name_intro_persons(self, text, results):
        add = []
        for rx in self.INTRO_PATTERNS:
            for m in rx.finditer(text):
                s, e = m.start(1), m.end(1)
                add.append(RecognizerResult("PERSON", s, e, 0.96))
        return self._resolve_overlaps(text, results + add) if add else results

    # ====================
    # Overlaps / filters
    # ====================
    def _resolve_overlaps(self, text, items):
        items = sorted(items, key=lambda r: (r.start, -self.PRIORITY.get(r.entity_type, 1), -(r.end - r.start)))
        kept = []
        for r in items:
            drop = False
            for k in kept:
                if not (r.end <= k.start or r.start >= k.end):
                    if self.PRIORITY.get(r.entity_type, 1) > self.PRIORITY.get(k.entity_type, 1) or \
                       (self.PRIORITY.get(r.entity_type, 1) == self.PRIORITY.get(k.entity_type, 1) and (r.end - r.start) > (k.end - k.start)):
                        kept.remove(k)
                        kept.append(r)
                    drop = True
                    break
            if not drop:
                kept.append(r)
        return sorted(kept, key=lambda x: x.start)

    def _demote_phone_over_date(self, text, items):
        dates = [(r.start, r.end) for r in items if r.entity_type == "DATE"]
        if not dates:
            return items
        out = []
        for r in items:
            if r.entity_type != "PHONE_NUMBER":
                out.append(r)
                continue
            if any(not (r.end <= ds or r.start >= de) for ds, de in dates):
                continue
            out.append(r)
        return out

    def _promote_meeting_over_phone(self, text, items, window: int = 20):
        out = []
        for r in items:
            if r.entity_type == "PHONE_NUMBER":
                left = text[max(0, r.start - window):r.start].lower()
                right = text[r.end:min(len(text), r.end + window)].lower()
                if "meeting id" in left or "meeting id" in right:
                    out.append(RecognizerResult("MEETING_ID", r.start, r.end, max(0.90, r.score)))
                    continue
            out.append(r)
        return self._resolve_overlaps(text, out)

    def _filter_label_leading_locations(self, text, items):
        tail_keywords = set(self.PASSPORT_KEYWORDS) | set(self.ID_KEYWORDS) | set(self.TAX_KEYWORDS)
        out = []
        for r in items:
            if r.entity_type == "LOCATION":
                tail = text[r.end:r.end + 24].lower()
                tail = re.sub(r"^[\s:,\-\–\—\|]+", "", tail)
                if any(tail.startswith(k) for k in tail_keywords):
                    continue
            out.append(r)
        return out

    def _filter_label_adjacent_locations(self, text, items, window: int = 26):
        label_tokens = set(self.PASSPORT_KEYWORDS) | set(self.ID_KEYWORDS) | set(self.TAX_KEYWORDS)
        out = []
        for r in items:
            if r.entity_type != "LOCATION":
                out.append(r)
                continue
            left = text[max(0, r.start - window):r.start].lower()
            right = text[r.end:min(len(text), r.end + window)].lower()
            left_norm = re.sub(r"[\s:,\-–—\|]+$", " ", left)
            right_norm = re.sub(r"^[\s:,\-–—\|]+", " ", right)
            if any(kw in left_norm for kw in label_tokens) or any(kw in right_norm for kw in label_tokens):
                continue
            out.append(r)
        return out

    def _guard_natural_suffix_requires_number(self, text: str, items, suffixes: tuple):
        if not items:
            return items
        out = []
        for r in items:
            if r.entity_type == "ADDRESS":
                span = text[r.start:r.end].strip()
                lower = span.lower()
                if any(lower.endswith(suf) for suf in suffixes):
                    if not re.search(r"\d", span):
                        continue
            out.append(r)
        return out

    def _guard_single_token_addresses(self, text: str, items):
        if not items:
            return items
        out = []
        for r in items:
            if r.entity_type == "ADDRESS":
                span = text[r.start:r.end].strip()
                if len(span.split()) == 1 and not re.search(r"\d", span):
                    continue
            out.append(r)
        return out

    def _guard_address_vs_person(self, items):
        if not items:
            return items
        persons = [p for p in items if p.entity_type == "PERSON"]
        if not persons:
            return items
        out = []
        for r in items:
            if r.entity_type == "ADDRESS":
                overlap_with_person = any(not (r.end <= p.start or r.start >= p.end) for p in persons)
                if overlap_with_person:
                    continue
            out.append(r)
        return out

    def _guard_requires_context(self, text: str, items, keywords: tuple, window: int):
        if not items:
            return items
        lower = text.lower()
        out = []
        for r in items:
            if r.entity_type == "ADDRESS":
                span = text[r.start:r.end]
                if not re.search(r"\d", span):
                    left = max(0, r.start - window)
                    right = min(len(text), r.end + window)
                    ctx = lower[left:right]
                    if not any(k in ctx for k in keywords):
                        continue
            out.append(r)
        return out

    def _trim_address_spans(self, text, items):
        """Trim ADDRESS spans at first newline or before label words to avoid bleed."""
        label_stops = re.compile(r"(?i)\b(email|e-mail|mail|meine|la mia email|mon email|adresse)\b")
        out = []
        for r in items:
            if r.entity_type != "ADDRESS":
                out.append(r)
                continue
            s, e = r.start, r.end
            span = text[s:e]
            cut = span.find("\n")
            if cut != -1:
                e = s + cut
            else:
                m = label_stops.search(span)
                if m:
                    e = s + m.start()
            trimmed = span[:e - s].rstrip(" .,:;–—")
            if trimmed:
                out.append(RecognizerResult("ADDRESS", s, s + len(trimmed), r.score))
            else:
                out.append(r)
        return self._resolve_overlaps(text, out)

    def _filter_idnumber_false_positives(self, text, items):
        out = []
        for r in items:
            if r.entity_type == "ID_NUMBER":
                span = text[r.start:r.end]
                if not re.search(r"\d", span):
                    # Pure alpha → drop
                    continue
                if re.fullmatch(r"[A-Za-z]{3,}", span):
                    continue
                # Drop obvious health/policy words
                if re.search(r"(?i)\b(insurance|policy|diagnosed|passeport|passport|kontonummer)\b", span):
                    continue
            out.append(r)
        return out

    # ====================
    # Helpers: Validations
    # ====================
    @staticmethod
    def _luhn_ok(digits: str) -> bool:
        if not digits.isdigit() or len(digits) < 13 or len(digits) > 19:
            return False
        total = 0
        rev = digits[::-1]
        for i, ch in enumerate(rev):
            n = ord(ch) - 48
            if i % 2 == 1:
                n *= 2
                if n > 9:
                    n -= 9
            total += n
        return total % 10 == 0

    @staticmethod
    def _iban_ok(iban: str) -> bool:
        s = re.sub(r"[\s\-]", "", iban).upper()
        if not re.match(r"^[A-Z]{2}\d{2}[A-Z0-9]{10,30}$", s):
            return False
        rarr = s[4:] + s[:4]
        conv = []
        for ch in rarr:
            if ch.isdigit():
                conv.append(ch)
            else:
                conv.append(str(ord(ch) - 55))
        num = "".join(conv)
        rem = 0
        for c in num:
            rem = (rem * 10 + (ord(c) - 48)) % 97
        return rem == 1

    @staticmethod
    def _aba_ok(nine: str) -> bool:
        if not re.fullmatch(r"\d{9}", nine):
            return False
        d = [int(x) for x in nine]
        checksum = (3 * (d[0] + d[3] + d[6]) + 7 * (d[1] + d[4] + d[7]) + (d[2] + d[5] + d[8])) % 10
        return checksum == 0

    @staticmethod
    def _imei_luhn_ok(candidate: str) -> bool:
        digits = re.sub(r"\D", "", candidate)
        if len(digits) != 15:
            return False
        total = 0
        rev = digits[::-1]
        for i, ch in enumerate(rev):
            n = ord(ch) - 48
            if i % 2 == 1:
                n *= 2
                if n > 9:
                    n -= 9
            total += n
        return total % 10 == 0

    @staticmethod
    def _nhs_ok(s: str) -> bool:
        digits = re.sub(r"\s", "", s)
        if not re.fullmatch(r"\d{10}", digits):
            return False
        weights = list(range(10, 1, -1))
        total = sum(int(digits[i]) * weights[i] for i in range(9))
        check = 11 - (total % 11)
        if check == 11:
            check = 0
        if check == 10:
            return False
        return check == int(digits[9])

    @staticmethod
    def _geo_in_bounds(lat: float, lon: float) -> bool:
        return -90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0

    # ====================
    # CUSTOM INJECTIONS
    # ====================
    def _inject_custom_matches(self, text, results):
        add = []

        # Addresses
        for m in self.STRICT_ADDRESS_RX.finditer(text):
            add.append(RecognizerResult("ADDRESS", m.start(), m.end(), 0.95))

        # Postal → LOCATION
        for patt in self.POSTAL_EU_PATTERNS:
            for m in re.finditer(patt, text, flags=re.I | re.UNICODE):
                add.append(RecognizerResult("LOCATION", m.start(), m.end(), 0.92))

        # Phones or Meeting IDs
        for m in self.PHONE_RX.finditer(text):
            s, e = m.start(), m.end()
            left = text[max(0, s - 24):s].lower()
            right = text[e:min(len(text), e + 24)].lower()
            if "meeting id" in left or "meeting id" in right:
                add.append(RecognizerResult("MEETING_ID", s, e, 0.90))
            else:
                if len(re.sub(r"\D", "", m.group())) >= 7:
                    add.append(RecognizerResult("PHONE_NUMBER", s, e, 0.90))

        # Fax (label-led)
        for fax in self.FAX_LABEL_RX.finditer(text):
            start = fax.end()
            seg = text[start:start + 64]
            m = re.search(r"(?:\+?\d{1,3}[ \-]?)?(?:\(?\d{1,4}\)?[ \-]?)?(?:\d[ \-]?){5,12}\d", seg)
            if m:
                s = start + m.start()
                e = start + m.end()
                add.append(RecognizerResult("FAX_NUMBER", s, e, 0.88))

        # Dates
        for patt in (self.DATE_REGEX_1, self.DATE_REGEX_2, self.DATE_REGEX_3):
            for m in re.finditer(patt, text, flags=re.I | re.UNICODE):
                add.append(RecognizerResult("DATE", m.start(), m.end(), 0.93))

        # IDs
        for patt, _name in self.ID_PATTERNS:
            for m in re.finditer(patt, text, flags=re.I | re.UNICODE):
                s, e = (m.start(1), m.end(1)) if m.lastindex else (m.start(), m.end())
                add.append(RecognizerResult("ID_NUMBER", s, e, 0.92))

        # TAX strict
        for patt, _name in self.TAX_PATTERNS_STRICT:
            for m in re.finditer(patt, text, flags=re.I | re.UNICODE):
                s, e = (m.start(1), m.end(1)) if m.lastindex else (m.start(), m.end())
                add.append(RecognizerResult("TAX_ID", s, e, 0.92))

        # TAX loose (optional + guarded)
        if self.ENABLE_LOOSE_TAX:
            for patt, _name in self.TAX_PATTERNS_LOOSE:
                for m in re.finditer(patt, text, flags=re.I | re.UNICODE):
                    s, e = (m.start(1), m.end(1)) if m.lastindex else (m.start(), m.end())
                    span = text[s:e]
                    left_ctx = text[max(0, s - 12):s].lower()
                    right_ctx = text[e:min(len(text), e + 12)].lower()
                    looks_like_date = bool(re.search(r"[./-]", span)) or any(k in left_ctx for k in ["born", "geb", "date", "dob"])
                    looks_like_phone = bool(re.search(r"[()\- ]", span)) or any(k in left_ctx for k in ["tel", "phone", "fax", "mob"])
                    looks_like_ip = bool(re.fullmatch(r"\d{1,3}", span)) and (("." in left_ctx or "." in right_ctx or ":" in left_ctx or ":" in right_ctx))
                    looks_like_coord = any(k in left_ctx for k in ["coord", "lat", "lon"])
                    if looks_like_date or looks_like_phone or looks_like_ip or looks_like_coord:
                        continue
                    add.append(RecognizerResult("TAX_ID", s, e, 0.86))

        # Label-based IDs & TAX
        for m in self.LABELED_ID_VALUE_RX.finditer(text):
            s, e = (m.start(1), m.end(1)) if m.lastindex else (m.start(), m.end())
            add.append(RecognizerResult("ID_NUMBER", s, e, 0.93))
        for m in self.LABELED_TAX_VALUE_RX.finditer(text):
            s, e = (m.start(1), m.end(1)) if m.lastindex else (m.start(), m.end())
            add.append(RecognizerResult("TAX_ID", s, e, 0.93))

        # US SSN/ITIN/EIN label-led
        for m in self.SSN_LABEL_RX.finditer(text):
            s, e = (m.start(1), m.end(1)) if m.lastindex else (m.start(), m.end())
            add.append(RecognizerResult("ID_NUMBER", s, e, 0.94))
        for m in self.ITIN_LABEL_RX.finditer(text):
            s, e = (m.start(1), m.end(1)) if m.lastindex else (m.start(), m.end())
            add.append(RecognizerResult("ID_NUMBER", s, e, 0.93))
        for m in self.EIN_LABEL_RX.finditer(text):
            s, e = (m.start(1), m.end(1)) if m.lastindex else (m.start(), m.end())
            add.append(RecognizerResult("ID_NUMBER", s, e, 0.93))

        # Passports
        for m in re.finditer(self.US_PASSPORT_REGEX, text):
            add.append(RecognizerResult("PASSPORT", m.start(), m.end(), 0.95))
        for m in re.finditer(self.EU_PASSPORT_REGEX, text):
            add.append(RecognizerResult("PASSPORT", m.start(), m.end(), 0.90))

        # IP
        for patt in (self.IPV4_REGEX, self.IPV6_REGEX):
            for m in re.finditer(patt, text, flags=re.I | re.UNICODE):
                add.append(RecognizerResult("IP_ADDRESS", m.start(), m.end(), 0.95))

        # Credit Cards
        for m in re.finditer(r"(?:(?<!\w)(?:\d[ -]?){13,19}\d(?!\w))", text, flags=re.I | re.UNICODE):
            raw = m.group()
            digits = re.sub(r"[^\d]", "", raw)
            if self._luhn_ok(digits):
                add.append(RecognizerResult("CREDIT_CARD", m.start(), m.end(), 0.96))
        for m in self.LABELED_CC_RX.finditer(text):
            s, e = (m.start(1), m.end(1)) if m.lastindex else (m.start(), m.end())
            raw = text[s:e]
            digits = re.sub(r"[^\d]", "", raw)
            if self._luhn_ok(digits):
                add.append(RecognizerResult("CREDIT_CARD", s, e, 0.97))

        # IBAN (validated)
        for m in self.IBAN_RX.finditer(text):
            if self._iban_ok(m.group()):
                add.append(RecognizerResult("BANK_ACCOUNT", m.start(), m.end(), 0.97))

        # BIC (uppercase + ISO check)
        for m in self.BIC_RX.finditer(text):
            if m.group(2) in self.ISO_COUNTRIES:
                add.append(RecognizerResult("BANK_ACCOUNT", m.start(), m.end(), 0.90))

        # Labeled bank/Account with guards
        for m in self.ACCT_LABEL_RX.finditer(text):
            s, e = (m.start(1), m.end(1)) if m.lastindex else (m.start(), m.end())
            val = text[s:e].strip()
            if '@' in val:
                continue
            if re.match(r'^[A-Za-z]{5,}$', val) and ' ' not in val:
                if not (self._iban_ok(val) or self.BIC_RX.fullmatch(val) or re.search(r'\d', val)):
                    continue
            if self._iban_ok(val):
                add.append(RecognizerResult("BANK_ACCOUNT", s, e, 0.98))
                continue
            m2 = self.BIC_RX.fullmatch(val)
            if m2 and m2.group(2) in self.ISO_COUNTRIES:
                add.append(RecognizerResult("BANK_ACCOUNT", s, e, 0.92))
                continue
            compact = re.sub(r"[^\w]", "", val)
            if 8 <= len(compact) <= 34 and re.match(r"^[A-Za-z0-9]+$", compact):
                add.append(RecognizerResult("ACCOUNT_NUMBER", s, e, 0.84))

        # Routing numbers (ABA)
        for m in self.ROUTING_RX.finditer(text):
            nine = m.group(1) if m.lastindex else m.group(0)
            s1, e1 = (m.start(1), m.end(1)) if m.lastindex else (m.start(0), m.end(0))
            if self._aba_ok(nine):
                add.append(RecognizerResult("ROUTING_NUMBER", s1, e1, 0.95))

        # Payment/API tokens
        for m in self.PAYMENT_TOKEN_RX.finditer(text):
            s, e = (m.start(1), m.end(1)) if m.lastindex else (m.start(), m.end())
            token = text[s:e]
            if len(token) >= 16:
                add.append(RecognizerResult("PAYMENT_TOKEN", s, e, 0.92))

        # Crypto
        for rx in (self.CRYPTO_BTC_LEGACY, self.CRYPTO_BTC_BECH32, self.CRYPTO_ETH):
            for m in rx.finditer(text):
                add.append(RecognizerResult("CRYPTO_ADDRESS", m.start(), m.end(), 0.90))

        # Health IDs & Info
        for m in self.HEALTH_ID_RX.finditer(text):
            s, e = (m.start(1), m.end(1)) if m.lastindex else (m.start(), m.end())
            val = text[s:e]
            if re.search(r"\b\d{3}\s*\d{3}\s*\d{4}\b", val) and self._nhs_ok(val):
                add.append(RecognizerResult("HEALTH_ID", s, e, 0.97))
            else:
                add.append(RecognizerResult("HEALTH_ID", s, e, 0.85))
        for m in self.MRN_RX.finditer(text):
            s, e = (m.start(1), m.end(1)) if m.lastindex else (m.start(), m.end())
            add.append(RecognizerResult("MRN", s, e, 0.90))
        for m in self.INSURANCE_ID_RX.finditer(text):
            s, e = (m.start(1), m.end(1)) if m.lastindex else (m.start(), m.end())
            add.append(RecognizerResult("INSURANCE_ID", s, e, 0.90))
        for m in self.HEALTH_INFO_RX.finditer(text):
            add.append(RecognizerResult("HEALTH_INFO", m.start(), m.end(), 0.80))

        # Education/Employment
        for m in self.STUDENT_NUMBER_RX.finditer(text):
            s, e = (m.start(1), m.end(1)) if m.lastindex else (m.start(), m.end())
            add.append(RecognizerResult("STUDENT_NUMBER", s, e, 0.88))
        for m in self.EMPLOYEE_ID_RX.finditer(text):
            s, e = (m.start(1), m.end(1)) if m.lastindex else (m.start(), m.end())
            add.append(RecognizerResult("EMPLOYEE_ID", s, e, 0.90))
        for m in self.PRO_LICENSE_RX.finditer(text):
            s, e = (m.start(1), m.end(1)) if m.lastindex else (m.start(), m.end())
            add.append(RecognizerResult("PRO_LICENSE", s, e, 0.88))

        # Contact/Comms
        for m in self.SOCIAL_HANDLE_RX.finditer(text):
            add.append(RecognizerResult("SOCIAL_HANDLE", m.start(), m.end(), 0.80))
        for m in self.DISCORD_ID_RX.finditer(text):
            add.append(RecognizerResult("MESSAGING_ID", m.start(), m.end(), 0.85))
        for m in self.MESSAGING_LABELED_RX.finditer(text):
            s, e = (m.start(1), m.end(1)) if m.lastindex else (m.start(), m.end())
            add.append(RecognizerResult("MESSAGING_ID", s, e, 0.84))
        for m in self.ZOOM_ID_RX.finditer(text):
            s, e = (m.start(1), m.end(1)) if m.lastindex else (m.start(), m.end())
            num = re.sub(r"[^\d]", "", text[s:e])
            if 9 <= len(num) <= 12:
                add.append(RecognizerResult("MEETING_ID", s, e, 0.88))
        for m in self.MEET_CODE_RX.finditer(text):
            add.append(RecognizerResult("MEETING_ID", m.start(1), m.end(1), 0.86))

        # Devices
        for m in self.MAC_RX.finditer(text):
            add.append(RecognizerResult("MAC_ADDRESS", m.start(), m.end(), 0.90))
        for m in self.IMEI_RX.finditer(text):
            if self._imei_luhn_ok(m.group()):
                add.append(RecognizerResult("IMEI", m.start(), m.end(), 0.94))
        for m in self.AD_ID_LABEL_RX.finditer(text):
            add.append(RecognizerResult("ADVERTISING_ID", m.start(1), m.end(1), 0.92))
        for m in self.DEVICE_ID_LABEL_RX.finditer(text):
            add.append(RecognizerResult("DEVICE_ID", m.start(1), m.end(1), 0.88))

        # Location extras
        for m in self.GEO_COORDS_RX.finditer(text):
            try:
                lat = float(m.group(1)); lon = float(m.group(2))
                if self._geo_in_bounds(lat, lon):
                    add.append(RecognizerResult("GEO_COORDINATES", m.start(), m.end(), 0.90))
            except Exception:
                pass
        for m in self.PLUS_CODE_RX.finditer(text):
            add.append(RecognizerResult("PLUS_CODE", m.start(), m.end(), 0.86))
        for m in self.W3W_RX.finditer(text):
            add.append(RecognizerResult("W3W", m.start(), m.end(), 0.85))
        for m in self.PLATE_LABEL_RX.finditer(text):
            s, e = (m.start(1), m.end(1)) if m.lastindex else (m.start(), m.end())
            plate = re.sub(r"\s+", " ", text[s:e]).strip()
            comp = re.sub(r"[\s\-]", "", plate)
            if 4 <= len(comp) <= 10:
                add.append(RecognizerResult("LICENSE_PLATE", s, e, 0.85))

        merged = self._resolve_overlaps(text, results + add)
        merged = self._filter_label_leading_locations(text, merged)
        merged = self._filter_label_adjacent_locations(text, merged, window=28)
        return merged

    def _merge_address_location(self, text, items):
        items = sorted(items, key=lambda r: r.start)
        merged = []
        i = 0
        while i < len(items):
            cur = items[i]
            if i + 1 < len(items):
                nxt = items[i + 1]
                between = text[cur.end:nxt.start]
                if (cur.entity_type == "ADDRESS" and nxt.entity_type == "LOCATION") or \
                   (cur.entity_type == "LOCATION" and nxt.entity_type == "ADDRESS"):
                    if re.fullmatch(r"(?:\s*(?:,|؛|،|;)?\s*|\s*[-–—]?\s*|\n)", between):
                        s = min(cur.start, nxt.start)
                        e = max(cur.end, nxt.end)
                        merged.append(RecognizerResult("ADDRESS", s, e, max(cur.score, nxt.score)))
                        i += 2
                        continue
            merged.append(cur)
            i += 1
        return self._resolve_overlaps(text, merged)

    # ====================
    # Public API
    # ====================
    def anonymize_text(
        self,
        text: str,
        *,
        guards_enabled: bool = True,
        guard_natural_suffix_requires_number: bool = True,
        guard_single_token_addresses: bool = True,
        guard_address_vs_person_priority: bool = True,
        guard_requires_context_without_number: bool = True,
        guard_context_window: int = 40
    ) -> str:
        if not text or not text.strip():
            return text

        try:
            lang = detect(text)
        except Exception:
            lang = "en"
        if lang not in getattr(self.analyzer, "supported_languages", {"en"}):
            lang = "en"

        base = self.analyzer.analyze(
            text=text,
            language=lang,
            entities=self.ALLOWED_ENTITIES,
            score_threshold=0.50
        )

        # PERSON cleanup
        filtered = []
        for r in base:
            if r.entity_type == "PERSON":
                span = text[r.start:r.end]
                trimmed, offset = self._trim_intro(span)
                if offset > 0:
                    ns = r.start + offset
                    if (r.end - ns) >= 2:
                        r = RecognizerResult("PERSON", ns, r.end, r.score)
                        span = trimmed
                if not self._plausible_person(span, text, r.start):
                    continue
            filtered.append(r)

        # Intro persons
        filtered = self._inject_name_intro_persons(text, filtered)

        # Custom injections
        final = self._inject_custom_matches(text, filtered)

        # Address guards
        if guards_enabled:
            if guard_natural_suffix_requires_number:
                final = self._guard_natural_suffix_requires_number(text, final, self.NATURAL_SUFFIXES)
            if guard_single_token_addresses:
                final = self._guard_single_token_addresses(text, final)
            if guard_address_vs_person_priority:
                final = self._guard_address_vs_person(final)
            if guard_requires_context_without_number:
                final = self._guard_requires_context(text, final, self.ADDRESS_CONTEXT_KEYWORDS, guard_context_window)

        # Phone/date & meeting promotion
        final = self._demote_phone_over_date(text, final)
        final = self._promote_meeting_over_phone(text, final, window=24)

        # Address span trimming
        final = self._trim_address_spans(text, final)

        # ID false-positive filter
        final = self._filter_idnumber_false_positives(text, final)

        # Merge address/location
        final = self._merge_address_location(text, final)

        # Replacements: single-escaped HTML tokens
        operators = {
            "PERSON":           OperatorConfig("replace", {"new_value": "&amp;lt;PERSON&amp;gt;"}),
            "EMAIL_ADDRESS":    OperatorConfig("replace", {"new_value": "&amp;lt;EMAIL&amp;gt;"}),
            "PHONE_NUMBER":     OperatorConfig("replace", {"new_value": "&amp;lt;PHONE&amp;gt;"}),
            "FAX_NUMBER":       OperatorConfig("replace", {"new_value": "&amp;lt;FAX&amp;gt;"}),
            "ADDRESS":          OperatorConfig("replace", {"new_value": "&amp;lt;ADDRESS&amp;gt;"}),
            "LOCATION":         OperatorConfig("replace", {"new_value": "&amp;lt;LOCATION&amp;gt;"}),
            "DATE":             OperatorConfig("replace", {"new_value": "&amp;lt;DATE&amp;gt;"}),
            "PASSPORT":         OperatorConfig("replace", {"new_value": "&amp;lt;PASSPORT&amp;gt;"}),
            "ID_NUMBER":        OperatorConfig("replace", {"new_value": "&amp;lt;ID_NUMBER&amp;gt;"}),
            "TAX_ID":           OperatorConfig("replace", {"new_value": "&amp;lt;TAX_ID&amp;gt;"}),
            "IP_ADDRESS":       OperatorConfig("replace", {"new_value": "&amp;lt;IP_ADDRESS&amp;gt;"}),

            "CREDIT_CARD":      OperatorConfig("replace", {"new_value": "&amp;lt;CREDIT_CARD&amp;gt;"}),
            "BANK_ACCOUNT":     OperatorConfig("replace", {"new_value": "&amp;lt;BANK_ACCOUNT&amp;gt;"}),
            "ROUTING_NUMBER":   OperatorConfig("replace", {"new_value": "&amp;lt;ROUTING_NUMBER&amp;gt;"}),
            "ACCOUNT_NUMBER":   OperatorConfig("replace", {"new_value": "&amp;lt;ACCOUNT_NUMBER&amp;gt;"}),
            "PAYMENT_TOKEN":    OperatorConfig("replace", {"new_value": "&amp;lt;PAYMENT_TOKEN&amp;gt;"}),
            "CRYPTO_ADDRESS":   OperatorConfig("replace", {"new_value": "&amp;lt;CRYPTO_ADDRESS&amp;gt;"}),

            "DRIVER_LICENSE":   OperatorConfig("replace", {"new_value": "&amp;lt;DRIVER_LICENSE&amp;gt;"}),
            "VOTER_ID":         OperatorConfig("replace", {"new_value": "&amp;lt;VOTER_ID&amp;gt;"}),
            "RESIDENCE_PERMIT": OperatorConfig("replace", {"new_value": "&amp;lt;RESIDENCE_PERMIT&amp;gt;"}),
            "BENEFIT_ID":       OperatorConfig("replace", {"new_value": "&amp;lt;BENEFIT_ID&amp;gt;"}),
            "MILITARY_ID":      OperatorConfig("replace", {"new_value": "&amp;lt;MILITARY_ID&amp;gt;"}),

            "HEALTH_ID":        OperatorConfig("replace", {"new_value": "&amp;lt;HEALTH_ID&amp;gt;"}),
            "MRN":              OperatorConfig("replace", {"new_value": "&amp;lt;MRN&amp;gt;"}),
            "INSURANCE_ID":     OperatorConfig("replace", {"new_value": "&amp;lt;INSURANCE_ID&amp;gt;"}),
            "HEALTH_INFO":      OperatorConfig("replace", {"new_value": "&amp;lt;HEALTH_INFO&amp;gt;"}),

            "STUDENT_NUMBER":   OperatorConfig("replace", {"new_value": "&amp;lt;STUDENT_NUMBER&amp;gt;"}),
            "EMPLOYEE_ID":      OperatorConfig("replace", {"new_value": "&amp;lt;EMPLOYEE_ID&amp;gt;"}),
            "PRO_LICENSE":      OperatorConfig("replace", {"new_value": "&amp;lt;PRO_LICENSE&amp;gt;"}),

            "SOCIAL_HANDLE":    OperatorConfig("replace", {"new_value": "&amp;lt;SOCIAL_HANDLE&amp;gt;"}),
            "MESSAGING_ID":     OperatorConfig("replace", {"new_value": "&amp;lt;MESSAGING_ID&amp;gt;"}),
            "MEETING_ID":       OperatorConfig("replace", {"new_value": "&amp;lt;MEETING_ID&amp;gt;"}),

            "MAC_ADDRESS":      OperatorConfig("replace", {"new_value": "&amp;lt;MAC_ADDRESS&amp;gt;"}),
            "IMEI":             OperatorConfig("replace", {"new_value": "&amp;lt;IMEI&amp;gt;"}),
            "ADVERTISING_ID":   OperatorConfig("replace", {"new_value": "&amp;lt;ADVERTISING_ID&amp;gt;"}),
            "DEVICE_ID":        OperatorConfig("replace", {"new_value": "&amp;lt;DEVICE_ID&amp;gt;"}),

            "GEO_COORDINATES":  OperatorConfig("replace", {"new_value": "&amp;lt;GEO_COORDINATES&amp;gt;"}),
            "PLUS_CODE":        OperatorConfig("replace", {"new_value": "&amp;lt;PLUS_CODE&amp;gt;"}),
            "W3W":              OperatorConfig("replace", {"new_value": "&amp;lt;W3W&amp;gt;"}),
            "LICENSE_PLATE":    OperatorConfig("replace", {"new_value": "&amp;lt;LICENSE_PLATE&amp;gt;"}),
        }

        out = self.anonymizer.anonymize(text=text, analyzer_results=final, operators=operators)
        return out.text
