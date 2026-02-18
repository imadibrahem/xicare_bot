
from presidio_analyzer import AnalyzerEngine, PatternRecognizer, Pattern, RecognizerResult
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig
from langdetect import detect
import re
import warnings
import logging
import unicodedata
import math

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
        "ADDRESS": 20,
        "PASSPORT": 7,
        "ID_NUMBER": 9,
        "DRIVER_LICENSE": 8,
        "VOTER_ID": 8,
        "RESIDENCE_PERMIT": 8,
        "BENEFIT_ID": 10,
        "MILITARY_ID": 10,

        "TAX_ID": 7,
        "CREDIT_CARD": 18,
        "BANK_ACCOUNT": 16,
        "ROUTING_NUMBER": 7,
        "ACCOUNT_NUMBER": 6,
        "PAYMENT_TOKEN": 6,
        "CRYPTO_ADDRESS": 6,

        "HEALTH_ID": 7,
        "MRN": 9,
        "INSURANCE_ID": 6,
        "HEALTH_INFO": 5,

        "STUDENT_NUMBER": 11,
        "EMPLOYEE_ID": 11,
        "PRO_LICENSE": 11,

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
        "IMEI": 17,
        "ADVERTISING_ID": 6,
        "DEVICE_ID": 5,

        "GEO_COORDINATES": 5,
        "PLUS_CODE": 9,
        "W3W": 4,
        "LICENSE_PLATE": 5,
        "COMMERCIAL_REGISTER": 9,
        "CASE_REFERENCE": 10,
        
        "BUND_ID": 8,
        "ELSTER_ID": 8,
        "SERVICEKONTO": 7,
        
        "PASSWORD": 8,
        "PIN": 9,
        "TAN": 7,
        "PUK": 9,
        "RECOVERY_CODE": 8,
        
        "FILE_NUMBER": 9,
        "TRANSACTION_NUMBER": 9,
        "CUSTOMER_NUMBER": 8,
        "TICKET_ID": 8,
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
        "API_KEY", "SESSION_ID", "ACCESS_TOKEN", "REFRESH_TOKEN", "ACCESS_CODE", "OTP_CODE",
        "EORI", "COMMERCIAL_REGISTER", "CASE_REFERENCE",
        "BUND_ID", "ELSTER_ID", "SERVICEKONTO",
        "PASSWORD", "PIN", "TAN", "PUK", "RECOVERY_CODE",
        "FILE_NUMBER", "TRANSACTION_NUMBER", "CUSTOMER_NUMBER", "TICKET_ID",
    ]

    def __init__(self, person_false_positive_samples=None, non_name_after_ich_bin=None):
        if person_false_positive_samples is None:
            person_false_positive_samples = []
        
        if non_name_after_ich_bin is None:
            non_name_after_ich_bin = []

        self.person_deny_list = person_false_positive_samples
        self.language = 'en'
        warnings.filterwarnings("ignore")
        logging.getLogger().setLevel(logging.ERROR)

        # Feature flag to include loose unlabeled TAX fallbacks (default off)
        self.ENABLE_LOOSE_TAX = False
        self.STRICT_LOCATION_POSTAL_ONLY = True
        self._build_patterns()
        self._setup_analyzer()
        # --- German-specific "not-a-name" tokens after "ich bin"
        self.DE_NON_NAME_AFTER_ICH_BIN = {
            "beschäftigt","arbeitslos","krank","gesund","müde","wach","allein","verheiratet",
            "ledig","getrennt","geschieden","verwitwet","selbstständig","selbststaendig",
            "angestellt","frei","verfügbar","verfuegbar","bereit","heute","gestern","morgen",
            "hier","da","dran","unterwegs","anwesend","abwesend","neu","alt","jung","schon",
            "sehr","einfach","immer","gerade","kurz","gleich","bald",
            "elektriker","student","studentin","schüler","schueler","schülerin","schuelerin",
            "fahrer","koch","köchin","koechin","bäcker","baecker","verkäufer","verkaeufer",
            "berater","entwickler","programmierer","mechaniker","arzt","ärztin","aerztin",
            "anwalt","anwältin","anwaeltin","lehrer","lehrerin","pfleger","pflegerin",
            "friseur","friseurin","handwerker","gastronom","gastronomin",
        }
        # normalize and merge runtime-provided words
        self.DE_NON_NAME_AFTER_ICH_BIN.update([w.strip().lower() for w in non_name_after_ich_bin if w and w.strip()])
        # also merge external deny list for consistency
        for _w in self.person_deny_list:
            if isinstance(_w, str) and _w.strip():
                self.DE_NON_NAME_AFTER_ICH_BIN.add(_w.strip().lower())

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
        [\s\.,]*
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
        # Conservative fallback: street name + suffix + house number (captures variants missed by STRICT_ADDRESS)
        # Accept either the compact suffix list or the broader street type list (cover English 'Street', 'Avenue', etc.)
        self.FALLBACK_STREET_RX = re.compile(
            r"\b[A-ZÀ-ÖØ-ÝÄÖÜ][\wÀ-ÖØ-öø-ÿÄÖÜäöüß'’\.-]*(?:\s+(?:" + self.STREET_SUFFIX_COMPOUND + r"|" + self.STREET_TYPES + r"))[\s\.,]*\d{1,4}[A-Za-z]?(?:\s*[-–]\s*\d+[A-Za-z]?)?\b",
            re.I | re.UNICODE
        )
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

        # Phone (precompiled; no inline flags) - stricter to avoid matching TAX IDs
        self.PHONE_REGEX = r"""
        (?<!\w)
        (?:\+\d{1,3}[ \-]?)?(?:\(\d{1,4}\)[ \-]?)?(?:\d[ \-]?){6,12}\d
        (?!\w)
        """
        self.PHONE_RX = re.compile(self.PHONE_REGEX, re.IGNORECASE | re.UNICODE | re.VERBOSE)

        # Date
        self.DATE_REGEX_1 = r"\b\d{1,2}[.\-/]\d{1,2}[.\-/]\d{2,4}\b"
        self.DATE_REGEX_2 = r"\b\d{4}[.\-/]\d{1,2}[.\-/]\d{1,2}\b"
        self.DATE_REGEX_3 = r"\b\d{1,2}\s+[A-Za-zÄÖÜäöüßÁÉÍÓÚáéíóúñç]+,?\s+\d{4}\b"  # Added ,? to handle commas
        self.DATE_REGEX_4 = r"\b[A-Z][a-z]+\s+\d{1,2},?\s+\d{4}\b"  # US format: Month Day, Year
        self.DATE_REGEX_5 = r"\b\d{1,2}\.\s+(?:Januar|Februar|März|April|Mai|Juni|Juli|August|September|Oktober|November|Dezember|Jan|Feb|Mär|Apr|Jun|Jul|Aug|Sep|Okt|Nov|Dez)\b\s+\d{4}\b"  # German format
        self.SSN_REGEX = r"\b\d{3}-\d{2}-\d{4}\b"  # US Social Security Number format

        # Passports / IDs (generic)
        self.US_PASSPORT_REGEX = r"\b[A-Z][0-9]{8}\b"
        self.EU_PASSPORT_REGEX = r"\b[A-Z]{1,2}\d{6,8}\b"

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
            (r"\b(\d{3}-\d{2}-\d{4})\b", "us_ssn"),
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

        # EORI — explicitly labeled forms (e.g., 'EORI: DE123456789000' or 'EORI DE123456789')
        # We'll match a two-letter country code followed by 6-20 alphanumeric/ dash characters
        self.EORI_RX = re.compile(r"(?i)\bEORI[:\s]*([A-Z]{2}\s?[A-Z0-9\-]{6,20})")

        # Handelsregister / Commercial Register — multilingual European support
        # Captures: Register Court + Division A/B + optional register number
        # Supports: German (Handelsregister, Abteilung A/B, HRB/HRA)
        #          French (Tribunal de Commerce, Registre A/B, RCS)
        #          Spanish (Registro Mercantil, Sección A/B)
        #          Italian (Registro delle Imprese, Sezione A/B, REA)
        #          Dutch (Handelsregister, Afdeling A/B)
        self.COMMERCIAL_REGISTER_RX = re.compile(
            r"(?i)(?:"
            # German: Amtsgericht/Registergericht City, Handelsregister/Abteilung [AB] [numbers]
            r"(?:amtsgericht|registergericht)\s+[\w\-äöüß\s]+[,;]?\s*(?:handelsregister|abteilung|abt\.?)\s+[AB]\s*(?:\s*[,;]?\s*(?:hr[ab]|number|nr\.?)\s*[:\-]?\s*\d+)?"
            r"|"
            # German: Registergericht variations with HRB/HRA numbers (complete capture)
            r"registergericht\s+[\w\-äöüß\s]+\s*[,;]\s*(?:abteilung|abt\.?)\s+[AB]\s*[,;]?\s*(?:hr[ab])\s+\d+"
            r"|"
            # French: Tribunal de Commerce CityName, Registre [AB] [optional numbers]
            r"tribunal\s+de\s+commerce\s+[\w\-àâäç\s']+\s*[,;]?\s*(?:registre|section|sect\.?)\s+[AB]\s*(?:\s*[,;]?\s*\d+)?"
            r"|"
            # French: RCS CityName [AB] [optional numbers] - shorthand form
            r"rcs\s+[\w\-àâäç\s']+\s+[AB](?:\s+\d+)?"
            r"|"
            # Spanish: Registro Mercantil CityName, Sección [AB] [optional numbers]
            r"(?:registro\s+mercantil|reg\.?\s+merc\.?)\s+[\w\s\-áéíóúñ]+\s*[,;]?\s*(?:sección|secc\.?|sect\.?)\s+[AB]\s*(?:\s*[,;]?\s*\d+)?"
            r"|"
            # Italian: Registro delle Imprese CityName, Sezione [AB] [optional numbers]
            r"registro\s+dell[e']?\s+imprese\s+[\w\s\-àèéìòù]+\s*[,;]?\s*(?:sezione|sez\.?)\s+[AB]\s*(?:\s*[,;]?\s*\d+)?"
            r"|"
            # Italian: REA CityName [optional numbers] - shorthand form
            r"rea\s+[\w\-àèéìòù\s]+(?:\s+\d+)?"
            r"|"
            # Dutch: Handelsregister CityName, Afdeling [AB] [optional numbers]
            r"handelsregister\s+[\w\s\-]+\s*[,;]?\s*(?:afdeling|afd\.?)\s+[AB]\s*(?:\s*[,;]?\s*\d+)?"
            r"|"
            # Dutch: KVK CityName [AB] [optional numbers] - shorthand form (with or without section letter)
            r"kvk\s+[\w\s\-]+(?:\s+[AB])?\s*(?:\s+\d+)?"
            r")",
            re.UNICODE | re.MULTILINE | re.IGNORECASE
        )

        # Case / Reference / Ticket / Customer Number — multilingual support
        # Require an identifier that contains at least one digit to avoid false positives
        self.CASE_REFERENCE_RX = re.compile(
            r"(?i)(?:\b(?:"
            # English
            r"(?:case\s*(?:id|no|number)|reference\s*(?:number|no|nr)|ticket\s*(?:id|no|number)|customer\s*(?:number|id)|ref\.?))\b[ \t:#\-]*"
            r"(?=(?:[A-Z0-9\-/]*\d))[A-Z0-9\-/]{3,40}"
            r"|"
            # German
            r"\b(?:aktenzeichen|vorgangsnummer|kundennummer|az|vn|kn)\b[ \t:#\-]*(?=(?:[A-Z0-9\-/äöüÄÖÜß]*\d))[A-Z0-9\-/äöüÄÖÜß]{3,40}"
            r"|"
            # French
            r"\b(?:num(?:e|é)ro\s+(?:de\s+)?dossier|dossier)\b[ \t:#\-]*(?=(?:[A-Z0-9\-/]*\d))[A-Z0-9\-/]{3,40}"
            r"|"
            # Spanish
            r"\b(?:n[úu]mero\s+(?:de\s+)?expediente|expediente)\b[ \t:#\-]*(?=(?:[A-Z0-9\-/]*\d))[A-Z0-9\-/]{3,40}"
            r"|"
            # Italian
            r"\b(?:numero\s+(?:di\s+)?pratica|pratica)\b[ \t:#\-]*(?=(?:[A-Z0-9\-/]*\d))[A-Z0-9\-/]{3,40}"
            r"|"
            # Turkish
            r"\b(?:dosya\s+numaras[ıi]|dosya)\b[ \t:#\-]*(?=(?:[A-Z0-9\-/]*\d))[A-Z0-9\-/]{3,40}"
            r"|"
            # Arabic (expect Latin-style identifiers after Arabic label)
            r"\b(?:رقم\s+(?:القضية|الملف|الدعوى))\b[ \t:#\-]*(?=(?:[A-Z0-9\-/]*\d))[A-Z0-9\-/]{3,40}"
            r")",
            re.UNICODE | re.MULTILINE | re.IGNORECASE,
        )

        # Label-based ID/TAX capture
        self.LABELED_ID_VALUE_RX = re.compile(
            r"(?i)\b(?:personalausweis(?:nummer|nr\.?)|identity\s*card|id\s*(?:no\.?|number)|dni|nif|nie|bsn|pesel|egn|cnp|amka|cpr|rodné\s*číslo|rodne\s*cislo|jmbg|emšo|emso)"
            r"\s*[:#]?\s*([A-Z0-9][A-Z0-9\-]{4,24})"
        )
        
        self.LABELED_TAX_VALUE_RX = re.compile(
             r"(?i)\b(?:steuer[-\s]*id|steueridentifikationsnummer|tin|tax\s*id|tax\s*number|vat|ust-?id(?:nr\.?)?|ustid|vies|nif|siren|siret|piva|p\.?iva|afm|utr|cvr|oib|nip|regon|dic|cui|eik|bulstat)"
                r"\s*[:#]?\s*("
                 r"(?=[A-Z]{2}\s*[A-Z0-9][A-Z0-9\.\-\s]{1,24})(?=.*\d)[A-Z]{2}\s*[A-Z0-9][A-Z0-9\.\-\s]{1,24}"
                 r"|(?=[A-Z0-9\-\s]{6,24})(?=.*\d)[A-Z0-9\-\s]{6,24}"
                    r")"
        )


        # US IDs: SSN/ITIN/EIN (label-led only)
        self.SSN_LABEL_RX = re.compile(r"(?i)\bssn\b[:#\-]?\s*(\d{3}-\d{2}-\d{4}|\d{9})")
        self.ITIN_LABEL_RX = re.compile(r"(?i)\bitin\b[:#\-]?\s*(\d{3}-\d{2}-\d{4}|\d{9})")
        self.EIN_LABEL_RX = re.compile(r"(?i)\bein\b[:#\-]?\s*(\d{2}-\d{7})")

        # German e-government identifiers
        # BundID: German Federal Digital Identity — format: BUND-XXXXXXXX-XXXX or similar
        self.BUND_ID_RX = re.compile(
            r"(?i)\b(?:"
            r"(?:bundid|bund[ \t]+id|bundidentität|bundes?ausweis|digital\s+identity\s+(?:number|id))[ \t:#\-]*"
            r"(?=(?:[A-Z0-9\-]{8,20})[^A-Z0-9\-]|[A-Z0-9\-]{8,20}$)"
            r"[A-Z0-9\-]{8,20}"
            r"|"
            r"BUND-[A-Z0-9]{8}-[A-Z0-9]{4}"
            r")",
            re.UNICODE | re.MULTILINE | re.IGNORECASE
        )
        
        # ELSTER_ID: German Tax Authority Login System (Elektronische Steuererklärung)
        # Formats: elster_username_12345, ELST-12345, elster_id_abc123, etc.
        self.ELSTER_ID_RX = re.compile(
            r"(?i)\b(?:"
            r"(?:elster(?:\s+|[\-_])?(?:id|login|benutzername|user(?:name)?|konto))[ \t:#\-]*"
            r"(?=(?:[A-Za-z0-9\-_.]{6,30})[^A-Za-z0-9\-_.]|[A-Za-z0-9\-_.]{6,30}$)"
            r"[A-Za-z0-9\-_.]{6,30}"
            r"|"
            r"ELST-[A-Z0-9]{5,8}"
            r"|"
            r"elster_[A-Za-z0-9]{8,20}"
            r"|"
            r"(?:steuerkennung|steuernummer)\s*[:#\-]\s*[A-Z0-9\-]{10,30}"
            r")",
            re.UNICODE | re.MULTILINE | re.IGNORECASE
        )
        
        # SERVICEKONTO: German government service account identifier
        # Formats: servicekonto_56789, SK-2024-001234, Service-Konto: 123456789, etc.
        self.SERVICEKONTO_RX = re.compile(
            r"(?i)\b(?:"
            r"(?:servicekonto|service[\s\-]?konto|service[\s\-]?account|government[\s\-]?account|state[\s\-]?service)[ \t:#\-]*"
            r"(?=(?:[A-Za-z0-9\-_.]{6,30})[^A-Za-z0-9\-_.]|[A-Za-z0-9\-_.]{6,30}$)"
            r"[A-Za-z0-9\-_.]{6,30}"
            r"|"
            r"SK-\d{4}-[A-Z0-9]{6,8}"
            r"|"
            r"servicekonto[ \t:#\-]*[A-Z0-9]{8,20}"
            r"|"
            r"(?:konto|account)(?:\s+id|[\-_]id)?[ \t:#\-]*[A-Z0-9\-]{6,30}"
            r")",
            re.UNICODE | re.MULTILINE | re.IGNORECASE
        )

        # Authentication Secrets — multilingual support
        # PASSWORD: requires explicit label to avoid false positives
        self.PASSWORD_RX = re.compile(
            r"(?:password|pwd|passwort|kennwort|mot\s+de\s+passe|contraseña|parola|wachtwoord|şifre|كلمة\s+المرور)"
            r"(?:\s+(?:is|ist|est))?[\s:#\-=]+"
            r"[A-Za-z0-9!@#$%^&*()_+\-=[\]{}|;':\"<>,.?/~`]{6,}",
            re.UNICODE | re.MULTILINE | re.IGNORECASE
        )
        
        # PIN: numeric or alphanumeric, usually 4-8 digits
        self.PIN_RX = re.compile(
            r"(?:pin|pin[\s\-]?code|pin[\s\-]?number|personal\s+id\s+number|personal\s+identification\s+number|personal\s+id|geheimzahl|code[\s\-]?secret|código[\s\-]?secreto|رمز)"
            r"[\s:#\-=]+"
            r"[0-9A-Z]{4,8}",
            re.UNICODE | re.MULTILINE | re.IGNORECASE
        )
        
        # TAN: transaction authentication number, usually 6-8 digits/alphanumeric
        self.TAN_RX = re.compile(
            r"(?:tan|tan[\s\-]?code|transaction[\s\-]?authentication[\s\-]?number|authentifizierungsnummer|numéro[\s\-]?authentification|número[\s\-]?autenticación|numero[\s\-]?autenticazione|رقم\s+المصادقة)"
            r"[\s:#\-=]+"
            r"[0-9A-Z]{6,8}",
            re.UNICODE | re.MULTILINE | re.IGNORECASE
        )
        
        # PUK: PIN unblocking key, usually 8-10 digits
        self.PUK_RX = re.compile(
            r"(?:puk|puk[\s\-]?code|pin[\s\-]?unlock[\s\-]?key|entsperrcode|clé[\s\-]?déblocage|clave[\s\-]?desbloqueo|chiave[\s\-]?sblocco|kilit[\s\-]?açma[\s\-]?kodu|رمز\s+فتح\s+الحظر)"
            r"[\s:#\-=]+"
            r"[0-9]{8,10}",
            re.UNICODE | re.MULTILINE | re.IGNORECASE
        )
        
        # RECOVERY_CODE / BACKUP_CODE: Alphanumeric with hyphens, usually 6-20 chars
        self.RECOVERY_CODE_RX = re.compile(
            r"(?:recovery|recovery[\s\-]?code|backup[\s\-]?code|wiederherstellungscode|sicherungscode|code[\s\-]?de[\s\-]?récupération|código[\s\-]?de[\s\-]?recuperación|codice[\s\-]?di[\s\-]?recupero|herstelcode|kurtarma[\s\-]?kodu|رمز\s+الاسترجاع)"
            r"(?:\s+is)?[\s:#\-=]+"
            r"[A-Z0-9\-]{6,20}",
            re.UNICODE | re.MULTILINE | re.IGNORECASE
        )

        # FILE_NUMBER: Labeled file identifiers (multilingual)
        self.FILE_NUMBER_RX = re.compile(
            r"(?:file[\s\-]?(?:number|no|id|no\.)|dossier[\s\-]?(?:number|no|id|no\.)|dossier-number|fichier[\s\-]?(?:number|no|id|no\.)|expediente[\s\-]?(?:number|no|id|no\.)|aktenzeich|fascicolo[\s\-]?(?:number|no|id|no\.)|dossier[\s\-]?(?:numéro|numero)|numero[\s\-]?fascicolo)"
            r"[\s:#\-=]+"
            r"(?:[A-Z]{2}[\s\-]?)?[A-Z0-9][\w\-\.]{4,24}",
            re.UNICODE | re.MULTILINE | re.IGNORECASE
        )

        # TRANSACTION_NUMBER: Labeled transaction identifiers (multilingual)
        self.TRANSACTION_NUMBER_RX = re.compile(
            r"(?:transaction[\s\-]?(?:number|no|id|no\.)|trans(?:action)?[\s\-]?(?:number|no|id|no\.)?|txn[\s\-]?(?:number|no|id|no\.)?|transacción|transacion|transacion[\s\-]?(?:número|numero|no|id)|transazione[\s\-]?(?:numero|no|id)|transactie[\s\-]?(?:nummer|no|id)|transaktions[\s\-]?(?:nummer|no|id)|transactional|numéro[\s\-]?transaction|numero[\s\-]?transaci|transact\-id|ref[\s\-]?(?:number|no)[\s\-]?trans)"
            r"[\s:#\-=]+"
            r"(?:[A-Z0-9]{2,4}[\s\-]?)?[0-9A-Z]{4,20}(?:[\s\-]?[0-9]{2,4})?",
            re.UNICODE | re.MULTILINE | re.IGNORECASE
        )

        # CUSTOMER_NUMBER: Labeled customer identifiers (multilingual)
        self.CUSTOMER_NUMBER_RX = re.compile(
            r"(?:customer[\s\-]?(?:number|no|id|no\.)|cust(?:omer)?[\s\-]?(?:number|no|id|no\.)?|client[\s\-]?(?:number|no|id|no\.)?|numero[\s\-]?(?:client|cliente)|numéro[\s\-]?(?:client|cliente)|kundennummer|kundenid|klientennummer|client[\-\s]?id|cliente[\s\-]?(?:numero|no|id)|codice[\s\-]?cliente|klantennummer|klantnummer|customer[\s\-]?id|clnumber|custid|cust[\s\-]?number)"
            r"[\s:#\-=]+"
            # Require at least one digit in the identifier to avoid matching plain names like 'Customer: John'
            r"(?:[A-Z0-9]{2,4}[\s\-]?)?(?=[A-Z0-9]*\d)[A-Z0-9]{4,20}",
            re.UNICODE | re.MULTILINE | re.IGNORECASE
        )

        # TICKET_ID: Labeled ticket/issue/task identifiers (multilingual)
        self.TICKET_ID_RX = re.compile(
            r"(?:issue[\s\-]?(?:number|no|id|no\.)|task[\s\-]?(?:number|no|id|no\.)|tâche[\s\-]?(?:numéro|numero|no|id)|tarea[\s\-]?(?:numero|no|id)|compito[\s\-]?(?:numero|no|id)|ticketnummer|ticket[\-\s]?id|issue[\-\s]?id|ticket\-number|tkt[\s\-]?(?:number|no|id|no\.)|problem[\s\-]?(?:id|number)|problem[\-\s]?id)"
            r"[\s:#\-=]+"
            r"(?:[A-Z]{2,4}[\s\-]?)?[A-Z0-9][\w\-\.]{4,24}",
            re.UNICODE | re.MULTILINE | re.IGNORECASE
        )

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
            "en": [
                r"\bmy name is\s+",
                r"\bi am called\s+",
            ],

            "de": [
                r"\bmein name ist\s+",
                r"\bich hei(?:ß|ss)e\s+",
                # Safe variant: "ich bin" only when the next token looks like a name
                r"\bich bin\s+(?=[A-ZÄÖÜ][a-zäöüß]+)",
            ],

            "fr": [
                r"\bje m(?:'|’)?appelle\s+",
                r"\bmon nom est\s+",
            ],

            "es": [
                r"\bme llamo\s+",
                r"\bmi nombre es\s+",
            ],

            "it": [
                r"\bmi chiamo\s+",
                r"\bil mio nome è\s+",
            ],

            "pt": [
                r"\bmeu nome é\s+",
                r"\bo meu nome é\s+",
                r"\bchamo-me\s+",
            ],

            "nl": [
                r"\bmijn naam is\s+",
                r"\bik heet\s+",
            ],

            "sv": [r"\bjag heter\s+"],
            "no": [r"\bjeg heter\s+"],
            "da": [r"\bjeg hedder\s+"],

            "fi": [
                r"\bminun nimeni on\s+",
                r"\bnimeni on\s+",
            ],

            "pl": [r"\bnazywam się\s+"],
            "cs": [r"\bjmenuji se\s+"],
            "sk": [r"\bvolám sa\s+"],
            "hu": [r"\ba nevem\s+", r"\bhívnak\s+"],

            "ro": [
                r"\bnumele meu este\s+",
                r"\bm[ăa] numesc\s+",
            ],

            "ru": [r"\bменя зовут\s+"],
            "uk": [r"\bмене звати\s+", r"\bмене звуть\s+"],
            "bg": [r"\bказвам се\s+"],
            "el": [r"\bμε λένε\s+", r"\bονομάζομαι\s+"],

            "tr": [
                r"\bbenim ad[ıi]m\s+",
                # This one stays *out* → r"\badım\s+" would be too risky
            ],

            "ar": [
                r"(?:^|\b)(?:اسمي|أنا اسمي)\s+",
            ],

            "hr": [r"\bzovem se\s+"],
            "bs": [r"\bzovem se\s+"],
            "sr": [r"\bzovem se\s+"],

            "lt": [r"\bmano vardas(?: yra)?\s+"],
            "lv": [r"\bmani sauc\s+"],
            "et": [r"\bminu nimi on\s+"],
            "is": [r"\bég heiti\s+"],
            "mt": [r"\bjisimni\s+"],
            "ga": [r"\bis é mo ainm\s+"],
        }

        self.INTRO_PATTERNS = []
        for starters in intro_map.values():
            for s in starters:
                pat = re.compile(s + r"([^\s,;:.]+(?:\s+[^\s,;:.]+){0,1})", re.IGNORECASE | re.UNICODE)
                self.INTRO_PATTERNS.append(pat)

        # PERSON negative lexicon / single-token blockers (extended)
        self.NON_PERSON_SINGLE_TOKENS = {
            "beschäftigt","einfach","heute","schon","sehr","bereit","müde","krank","gesund","frei",
            "meine","mein","meiner"," ist","und","y","mi","il","la","el","le","les","de","des","del","da",
            "sono","soy","ich","bin","am","i","je","j'","j’","yo","tu","vos","vous","nous","vous",
            "abito","vivo","habito","wohne","adresse","liegt","indirizzo","dirección","direccion","direccio",
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
            "passeport","passport","domicile","meine nummer","meine", "nummer",
            # Added conversational/greeting tokens to reduce false positives
            "rund","überall","über","danke","dank","können","kann","nein","entschuldigen",
            "guten","gute","abend","morgen","nacht","wie","bitte","mir","helfen","das","macht","nichts",
            "aktualisierung","lösung","ok","okay","si","no",
            # Added German tokens to avoid single-token PERSON false positives
            "berg","groß","gross","klein","kalt","weil","neben","außer","ausser","gewerbe",
            # German days of week, time periods, directions, and common words
            "montag","dienstag","mittwoch","donnerstag","freitag","samstag","sonntag",
            "januar","februar","märz","april","mai","juni","juli","august","september","oktober","november","dezember",
            "morgen","mittag","abend","nacht","tag","woche","monat","jahr",
            "links","rechts","oben","unten","oben","vorne","hinten","innen","außen",
            "langsam","schnell","groß","klein","alt","jung","neu","gut","schlecht","schön",
            "hier","dort","da","wo","wann","wie","warum","was","welcher","welche","welches",
            "runter","hoch","rauf","runter","entlang","hinter","dienst","doktor","zwischen",
            # German business/action nouns and verbs that should not be person names
            "gründung","gründer","unternehmen","gibt","hat","habe","haben","sein",
            "beratung","beratungszentrum","beratungszentern","zentrum","zentren",
            "service","angebot","lösung","bieten","anbieten","anfrage",
        }

        self.PERSON_BLACKLIST_WORDS = {
            "personalausweisnummer","kontonummer","insurance","policy","diagnosed",
            "passeport","passport","domicile","meine nummer","bridi", "البريد", "الإلكتروني", "هاتفي", "عنواني",
            "gasse","ruf","mich","ولدت","koordinaten","gasse"
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

        # Titles that can introduce a following single-token person name
        self.TITLE_TOKENS = {"herr","frau","mr","mrs","ms","dr","prof","professor","doktor"}

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

        # Simple substring cues used for quick prefix checks (lowercased)
        self.INTRO_CUES = [
        "my name is", "je m", "mein name", "ich hei", "me llamo", "mi chiamo",
        "i am called",
        "meu nome", "chamo-me", "ik heet", "mijn naam", "jag heter", "jeg heter", "jeg hedder",
        "minun nimeni", "nimeni on", "ég heiti", "nazywam", "jmenuji se", "volám sa", "volam sa",
        "a nevem", "hívnak", "ma numesc", "mă numesc", "казвам се", "με λένε", "ονομάζομαι",
        "quhem", "ime mi je", "zovem se", "mano vardas", "mani sauc", "minu nimi on",
        "jisimni", "is é mo ainm", "benim adım", "اسمي", "меня зовут", "мене звати", "мене звуть", "мяне завуць",
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
            # Added localized ID label tokens
            "fødselsnummer", "fodselsnummer", "hetu", "personnummer", "fnr",
        })

        # Account-related label tokens (used to avoid misclassifying account/routing numbers as generic ID_NUMBER)
        self.ACCOUNT_LABELS = {"konto","kontonummer","bankleitzahl","bank","routing","account","iban","bic","kontonr"} 
        self.TAX_KEYWORDS = tuple({
            "tax id","tin","vat","vat id","vat no","vat number","vies",
            "steuer-id","steueridentifikationsnummer","steuernummer","ust-idnr","ustid","mwst",
            "numéro fiscal","numero fiscal","numéro de tva","tva","siren","siret",
            "nif","cif","iva",
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
            rf"(?i)\b{bank_labels}(?:\s*(?:[:#\-]?\s*|(?:is|ist)\s+))([A-Z0-9][A-Z0-9 \-]{{6,64}})",
            re.UNICODE
        )
        self.LABELED_CC_RX = re.compile(
            rf"(?i)\b{card_labels}(?:\s*(?:[:#\-]?\s*|(?:is|ist)\s+))(([0-9][0-9 \-]{{11,25}}[0-9]))",
            re.UNICODE
        )
        self.ROUTING_RX = re.compile(r"(?<!\d)(\d{9})(?!\d)")
        self.ACCT_LABEL_RX = re.compile(
            rf"(?i)\b(?:{bank_labels})(?:[:#\-]\s*|\s+(?:is|ist)\s+|\s+)([A-Z0-9][A-Z0-9 \-]{{6,34}})",
            re.UNICODE
        )
        self.PAYMENT_TOKEN_RX = re.compile(
            # Match labeled tokens (e.g., "token: <value>") OR common payment token prefixes like tok_...
            r"(?i)(?:\b(?:token|payment\s*token|client\s*secret|secret(?:\s*key)?|bearer\s*token)\b[:=\s\-]*([A-Za-z0-9_\-]{16,128})|\b(tok_[A-Za-z0-9]{8,64})\b)"
        )

        # ============================================================
        # Provider‑Specific API Key Patterns (clean + precise)
        # ============================================================
        self.API_KEY_PROVIDER_PATTERNS = [
            # AWS Access Key (AKIA or ASIA followed by 12-20 chars to handle various formats)
            (r"\b(?:AKIA|ASIA)[A-Z0-9]{12,20}\b", "aws_access_key"),

            # AWS Secret Key (labeled — 40 chars base64-like)
            (r"(?i)(?:aws_secret_access_key|aws_secret_key)\s*[:=]\s*([A-Za-z0-9/+=]{40})", "aws_secret_key_labeled"),

            # Stripe Keys (both test and live, both public and secret) - allow 10+ chars to match test keys
            (r"\b(?:sk|pk)_(?:live|test)_[0-9a-zA-Z]{10,}\b", "stripe_key"),

            # GitHub Tokens (all variants)
            (r"\bgithub_pat_[A-Za-z0-9_]{30,}\b", "github_pat"),
            (r"\bghp_[A-Za-z0-9]{36,}\b", "github_personal_access"),
            (r"\bgho_[A-Za-z0-9]{36,}\b", "github_oauth"),
            (r"\bghu_[A-Za-z0-9]{36,}\b", "github_user_to_server"),
            (r"\bghs_[A-Za-z0-9]{36,}\b", "github_server_to_server"),

            # Google / Firebase API Keys
            (r"\bAIza[0-9A-Za-z\-_]{32,}\b", "google_api"),

            # SendGrid
            (r"\bSG\.[A-Za-z0-9\-_]{22,}\b", "sendgrid"),

            # DigitalOcean
            (r"\bdop_v1_[A-Za-z0-9\-_]{40,}\b", "digitalocean"),

            # OpenAI (sk-proj patterns)
            (r"\bsk-proj-[A-Za-z0-9\-_]{20,}\b", "openai_project"),

            # Slack Bot/User tokens (xoxb/xoxp prefixes)
            (r"\bxoxb-[A-Za-z0-9\-]{10,}\b", "slack_bot_token"),
            (r"\bxoxp-[A-Za-z0-9\-]{10,}\b", "slack_user_token"),

            # Webhook Secrets (labeled or whsec prefix)
            (r"\bwhsec_[A-Za-z0-9_]{32,}\b", "webhook_secret"),

            # Twilio Auth Tokens (SK prefix + 32 chars)
            (r"\bSK[a-f0-9]{32}\b", "twilio_auth"),

            # Mailchimp API Keys (32 hex + -us region)
            (r"\b[a-f0-9]{32}\-us\d+\b", "mailchimp_api"),

            # JWT Bearer tokens (eyJ prefix)
            (r"\beyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\b", "jwt"),
        ]

        # compile them
        self.API_KEY_PROVIDER_RXS = [
            (re.compile(patt, re.UNICODE), name)
            for patt, name in self.API_KEY_PROVIDER_PATTERNS
        ]

        # Session, Access Token, Refresh Token patterns
        # ORDER MATTERS - more specific patterns should come first
        self.TOKEN_PATTERNS = [
            # SESSION_ID patterns (must come before generic "token")
            (r"(?i)sessionid\s*=\s*([A-Za-z0-9_\-]{12,})", "session_id_labeled"),
            (r"(?i)session_token\s*=\s*([A-Za-z0-9_\-]{12,})", "session_token_labeled"),
            (r"(?i)session_id\s*=\s*([A-Za-z0-9_\-]{12,})", "session_id_alt"),
            (r"(?i)sid\s*=\s*([A-Za-z0-9_\-]{12,})", "sid_labeled"),
            # REFRESH_TOKEN patterns (must come before generic "token")
            (r"(?i)refresh_token\s*=\s*([A-Za-z0-9_\-\.]{12,})", "refresh_token_labeled"),
            (r"(?i)refreshtoken\s*=\s*([A-Za-z0-9_\-\.]{12,})", "refresh_token_alt"),
            # ACCESS_TOKEN patterns (generic last, with word boundary to avoid being inside refresh_token)
            (r"(?i)access_token\s*=\s*([A-Za-z0-9_\-\.]{12,})", "access_token_labeled"),
            (r"(?i)bearer\s+([A-Za-z0-9_\-\.]{16,})", "bearer_token"),
            (r"(?i)\btoken\s*=\s*([A-Za-z0-9_\-\.]{12,})", "token_labeled"),
            # OTP_CODE patterns (must come before generic "code" to avoid false matches)
            (r"(?i)(?:otp|one.?time|2fa|two.?factor)[\s\w]*[:=]\s*([0-9]{4,8})", "otp_code_labeled"),
            (r"(?i)verification[\s\w]*code\s*[:=]\s*([0-9]{4,8})", "verification_code"),
            (r"(?i)mfa[\s\w]*code\s*[:=]\s*([0-9]{4,8})", "mfa_code"),
            # ACCESS_CODE patterns
            (r"(?i)(?:access|auth)[\s\w]*code\s*[:=]\s*([A-Za-z0-9]{4,8})", "access_code_labeled"),
            (r"(?i)pin[\s\w]*[:=]\s*([0-9]{4,6})", "pin_code"),
            # Generic "code" pattern (must come after specific OTP patterns to avoid overlap)
            (r"(?i)\bcode[\s\w]*[:=]\s*([A-Za-z0-9]{4,8})", "code_labeled"),
        ]
        # Compile Token patterns
        self.TOKEN_RXS = [(re.compile(patt, re.UNICODE), name) for patt, name in self.TOKEN_PATTERNS]
        # Crypto patterns
        self.CRYPTO_BTC_LEGACY = re.compile(r"\b[13][a-km-zA-HJ-NP-Z1-9]{26,33}\b")
        self.CRYPTO_BTC_BECH32 = re.compile(r"\b(?:bc1)[0-9a-z]{11,71}\b")
        self.CRYPTO_ETH = re.compile(r"\b0x[a-fA-F0-9]{40}\b")

        # Health patterns
        self.NHS_CAND_RX = re.compile(r"\b(?:(\d{3})\s*(\d{3})\s*(\d{4}))\b")
        self.MRN_RX = re.compile(r"(?i)\b(?:mrn|medical\s*record\s*number|krankenaktennummer|numéro\s*de\s*dossier|aktenzeichen)\b[:#\-]?\s*(?:(?:is|ist)\s+)?([A-Z0-9\-]{6,18})")
        self.INSURANCE_ID_RX = re.compile(r"(?i)\b(?:insurance\s*(?:id|policy|member)\b|versicherungspolice|versicherungsnummer|policen(?:nummer)?|nº\s*poliza)\b[:#\-]?\s*(?:(?:is|ist)\s+)?([A-Z0-9\-]{6,20})")
        self.HEALTH_ID_RX = re.compile(r"(?i)\b(?:health\s*id|patient\s*id|nhs\s*number|nhs[-_\s]?nummer)\b[:#\-]?\s*(?:(?:is|ist)\s+)?([A-Z0-9 \-]{6,20})")
        self.HEALTH_INFO_RX = re.compile(r"(?i)\b(?:diagnos(?:is|ed)|icd\-?10|icd\-?9|hiv|cancer|diabetes|pregnan(?:t|cy)|medicat(?:ion|e)|prescription|allerg(?:y|ies)|blood\s*type)\b")

        # Education/Employment
        self.STUDENT_NUMBER_RX = re.compile(r"(?i)\b(?:student\s*(?:id|number|ausweis(?:nummer)?)|matriculation|matrikel(?:nummer)?|matricula|roll\s*number)\b[:#\-]?\s*(?:(?:is|ist)\s+)?([A-Z0-9\-]{4,16})|\b(?:STU)[\-_]?[A-Z0-9]{3,10}\b")
        self.EMPLOYEE_ID_RX = re.compile(r"(?i)\b(?:employee\s*(?:id|number)|staff\s*id|mitarbeiter(?:nummer)?|personalnummer|personnel\s*number)\b[:#\-]?\s*([A-Z0-9\-]{4,16})|\b(?:EMP)[\-_]?[A-Z0-9]{3,10}\b")
        self.PRO_LICENSE_RX = re.compile(r"(?i)\b(?:license\s*(?:no|number|lizenz)|bar\s*number|medical\s*license|professional\s*license|berufslizenz)\b[:#\-]?\s*([A-Z0-9\-]{4,20})|\b(?:LIC)[\-_]?[A-Z0-9]{3,10}\b")

        # ID Documents - labeled (supports "My X is Y" and German "Meine X ist Y")
        self.DRIVER_LICENSE_LABEL_RX = re.compile(r"(?i)(?:my\s+|meine\s+)?(?:driver(?:'?s)?\s*(?:license|licence|lic)|dl\s*number|führerschein)\b(?:\s*(?:is|ist))?[\s:]*([A-Z]\d{5,10})")
        self.VOTER_ID_LABEL_RX = re.compile(r"(?i)(?:my\s+|meine\s+)?(?:voter\s*(?:id|card|number)|wähler(?:ausweis)?(?:nummer)?)\b(?:\s*(?:is|ist))?[\s:]*([A-Z]\d{5,10})")
        self.RESIDENCE_PERMIT_LABEL_RX = re.compile(r"(?i)(?:my\s+|meine\s+)?(?:residence\s*(?:permit|card)|resident\s*permit|aufenthaltsgenehmigung|aufenthaltstitel)\b(?:\s*(?:is|ist))?[\s:]*([A-Z]{2}\d{5,10})")
        self.BENEFIT_ID_LABEL_RX = re.compile(r"(?i)(?:my\s+|meine\s+)?(?:benefit\s*(?:id|card|number)|sozialhilf(?:e|ekarte))\b(?:\s+(?:is|ist))?[\s:]*([A-Z]\d{5,10})|\b(?:B)\d{7,10}\b")
        self.MILITARY_ID_LABEL_RX = re.compile(r"(?i)(?:my\s+|meine(?:r)?\s+)?(?:military\s*(?:id|number)|militär(?:ausweis)?)\b(?:\s+(?:is|ist))?[\s:]*([A-Z]\d{5,10})|\b(?:M)\d{7,10}\b")

        # Contact/Comms
        self.SOCIAL_HANDLE_RX = re.compile(r"(?<![\w@])@([A-Za-z0-9_]{3,32})(?![^\s@]*\.[^\s@])")
        self.DISCORD_ID_RX = re.compile(r"\b([A-Za-z0-9._\-]{2,32}#\d{4})\b")
        self.MESSAGING_LABELED_RX = re.compile(r"(?i)\b(?:telegram|skype|signal|wechat|line)\b[:#\-]?\s*([A-Za-z0-9._\-]{2,64})")
        self.ZOOM_ID_RX = re.compile(r"(?i)\b(?:meeting\s*id|zoom\s*id)\b[:#\-]?\s*([0-9][0-9 \-]{7,13}[0-9])")
        self.MEET_CODE_RX = re.compile(r"\b([a-z]{3}-[a-z]{4}-[a-z]{3,4})\b")

        self.FAX_LABEL_RX = re.compile(r"(?i)\bfax(?:nummer)?\b[:\s\-]*")
        # Email detection (used to prevent partial replacements inside email addresses)
        self.EMAIL_RX = re.compile(r"[\w\.\-+%]+@[\w\.\-]+\.[A-Za-z]{2,}", re.IGNORECASE)

        # Devices/Network
        self.MAC_RX = re.compile(r"\b(?:[0-9A-F]{2}[:-]){5}[0-9A-F]{2}\b|\b[0-9A-F]{12}\b", re.IGNORECASE)
        self.IMEI_RX = re.compile(r"\b(?:\d[ \-]?){14}\d\b")
        self.UUID_RX = re.compile(r"\b[0-9a-fA-F]{8}\-[0-9a-fA-F]{4}\-[0-9a-fA-F]{4}\-[0-9a-fA-F]{4}\-[0-9a-fA-F]{12}\b")
        self.AD_ID_LABEL_RX = re.compile(r"(?i)\b(?:idfa|aaid|advertis(?:ing)?\s*id)\b(?:\s*(?:[:#\-]?\s*|(?:is|ist)\s+))(" + self.UUID_RX.pattern + r")")
        self.DEVICE_ID_LABEL_RX = re.compile(r"(?i)\b(?:device\s*id|udid|Geräte\s*-?\s*id)\b(?:\s*(?:[:#\-]?\s*|(?:is|ist)\s+))(" + self.UUID_RX.pattern + r")")
        self.DEVICE_ID_PREFIX_RX = re.compile(r"(?i)\b(?:device\s*id|Geräte\s*-?\s*id)\b[:#\-]?\s*(?:(?:is|ist)\s+)?(\bDEV-\d{8,9}\b)")  # DEV-... format

        # Location extras
        self.GEO_COORDS_RX = re.compile(r"\b([+-]?\d{1,2}\.\d+)[,\s]+([+-]?\d{1,3}\.\d+)\b")
        self.PLUS_CODE_RX = re.compile(r"\b[23456789CFGHJMPQRVWX]{2,8}\+[23456789CFGHJMPQRVWX]{2,3}\b")
        self.W3W_RX = re.compile(r"\b///([a-z]+(?:\.[a-z]+){2,})\b")
        self.PLATE_LABEL_RX = re.compile(r"(?i)\b(?:license\s*plate|registration|plate\s*no|matr[ií]cula|targa|immatriculation|kennzeichen|număr\s*de\s*înmatriculare|车牌|plate)\b[:#\-]?\s*([A-Z0-9\- ]{4,12})")

        # Location extras
        self.GEO_COORDS_RX = re.compile(r"\b([+-]?\d{1,2}\.\d+)[,\s]+([+-]?\d{1,3}\.\d+)\b")
        self.PLUS_CODE_RX = re.compile(r"\b[23456789CFGHJMPQRVWX]{2,8}\+[23456789CFGHJMPQRVWX]{2,3}\b")
        self.W3W_RX = re.compile(r"\b///([a-z]+(?:\.[a-z]+){2,})\b")
        self.PLATE_LABEL_RX = re.compile(r"(?i)\b(?:license\s*plate|registration|plate\s*no|matr[ií]cula|targa|immatriculation|kennzeichen|număr\s*de\s*înmatriculare|车牌|plate)\b[:#\-]?\s*([A-Z0-9\- ]{4,12})")

    # ====================
    # Analyzer setup
    # ====================
    def _setup_analyzer(self):
        from presidio_analyzer import RecognizerRegistry
        self.analyzer = AnalyzerEngine(registry=RecognizerRegistry(recognizers=[]))
        self.anonymizer = AnonymizerEngine()
        
        # Remove conflicting default recognizers, keep only the ones we want
        self.analyzer.registry.recognizers = [
            r for r in self.analyzer.registry.recognizers 
            if r.name in ['DateRecognizer', 'EmailRecognizer', 'UrlRecognizer', 'SpacyRecognizer']
        ]

        self.address_recognizer = PatternRecognizer(
            supported_entity="ADDRESS", supported_language="all",
            patterns=[Pattern("strict_address", self.STRICT_ADDRESS_REGEX, 1.0)],
        )
        phone_compact = r"(?<!\w)\+?\d{1,3}[ -]?\d{1,4}[ -]?\d{4,}\b"
        self.phone_recognizer = PatternRecognizer(
            supported_entity="PHONE_NUMBER", supported_language="all",
            patterns=[Pattern("intl_phone", phone_compact, 1.0)],
        )
        self.date_recognizer = PatternRecognizer(
            supported_entity="DATE", supported_language="all",
            patterns=[Pattern("dob_1", self.DATE_REGEX_1, 1.0),
                      Pattern("dob_2", self.DATE_REGEX_2, 1.0),
                      Pattern("dob_3", self.DATE_REGEX_3, 1.0),
                      Pattern("german_date", r"\b\d{1,2}\. [A-ZÄÖÜ][a-zäöüß]+ \d{4}\b", 1.0),
                      Pattern("us_date", r"\b[A-Z][a-z]+\s+\d{1,2},?\s+\d{4}\b", 1.0)],
        )
        self.passport_recognizer = PatternRecognizer(
            supported_entity="PASSPORT", supported_language="all",
            patterns=[Pattern("us_passport", self.US_PASSPORT_REGEX, 1.02),
                      Pattern("eu_passport_generic", self.EU_PASSPORT_REGEX, 1.02)],
        )
        self.id_recognizer = PatternRecognizer(
            supported_entity="ID_NUMBER", supported_language="all",
            patterns=[Pattern("de_personalausweis", r"\b(?=[A-Z0-9]{9}\b)(?=.*[A-Z])[A-Z0-9]{9}\b", 1.0),
                      Pattern("ssn", r"\b\d{3}-\d{2}-\d{4}\b", 1.0)],
        )
        self.ip_recognizer = PatternRecognizer(
            supported_entity="IP_ADDRESS", supported_language="all",
            patterns=[Pattern("ipv4", self.IPV4_REGEX, 1.0),
                      Pattern("ipv6", self.IPV6_REGEX, 1.0)],
        )
        self.mac_recognizer = PatternRecognizer(
            supported_entity="MAC_ADDRESS", supported_language="all",
            patterns=[Pattern("mac", self.MAC_RX.pattern, 1.0)],
        )
        self.imei_recognizer = PatternRecognizer(
            supported_entity="IMEI", supported_language="all",
            patterns=[Pattern("imei", self.IMEI_RX.pattern, 1.0)],
        )
        self.cc_recognizer = PatternRecognizer(
            supported_entity="CREDIT_CARD", supported_language="all",
            patterns=[Pattern("cc_pan", r"(?:(?<!\w)(?:\d[ -]?){13,19}\d(?!\w))", 1.0)],
        )
        self.bank_recognizer = PatternRecognizer(
            supported_entity="BANK_ACCOUNT", supported_language="all",
            patterns=[Pattern("iban", self.IBAN_RX.pattern, 1.0),
                      Pattern("bic", self.BIC_RX.pattern, 1.0)],
        )
        self.health_recognizer = PatternRecognizer(
            supported_entity="HEALTH_INFO", supported_language="all",
            patterns=[Pattern("health_terms", r"(?i)\b(?:allergic|diagnosed|blood\s*type|diabetes|hypertension|asthma|cancer|heart\s*disease|penicillin|insulin|medication)\b", 1.0)],
        )

        self.plate_recognizer = PatternRecognizer(
            supported_entity="LICENSE_PLATE", supported_language="all",
            patterns=[Pattern("plate", self.PLATE_LABEL_RX.pattern, 1.0)],
        )

        self.person_recognizer = PatternRecognizer(
            supported_entity="PERSON", supported_language="all",
            # Require at least two capitalized tokens by default to reduce single-token false positives
            patterns=[Pattern("person", r"\b[A-Za-zÀ-ÖØ-öø-ÿ][A-Za-zÀ-ÖØ-öø-ÿ'’-]+(?:\s+[A-Za-zÀ-ÖØ-öø-ÿ][A-Za-zÀ-ÖØ-öø-ÿ'’-]+){0,3}", 1.0)],
            deny_list=self.person_deny_list
        )

        additional_recognizers = [
            PatternRecognizer(
                supported_entity="ACCOUNT_NUMBER", supported_language="all",
                patterns=[Pattern("account_number", r"\b\d{10}\b", 1.0)],
            ),
            PatternRecognizer(
                supported_entity="PAYMENT_TOKEN", supported_language="all",
                patterns=[Pattern("payment_token", r"\bsk_live_[a-zA-Z0-9]{10,30}\b", 1.0)],
            ),
            PatternRecognizer(
                supported_entity="ADVERTISING_ID", supported_language="all",
                patterns=[Pattern("advertising_id", r"\b[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}\b", 1.0)],
            ),
            PatternRecognizer(
                supported_entity="MRN", supported_language="all",
                patterns=[Pattern("mrn", r"\b[A-Z]{3}-\d{6}\b", 1.0)],
            ),
            PatternRecognizer(
                supported_entity="INSURANCE_ID", supported_language="all",
                patterns=[Pattern("insurance_id", r"\bPOL-\d{9}\b", 1.0)],
            ),
            PatternRecognizer(
                supported_entity="STUDENT_NUMBER", supported_language="all",
                patterns=[Pattern("student_number", r"\bSTU-\d{5}\b", 1.05)],
            ),
            PatternRecognizer(
                supported_entity="EMPLOYEE_ID", supported_language="all",
                patterns=[Pattern("employee_id", r"\bEMP-\d{5}\b", 1.0)],
            ),
            PatternRecognizer(
                supported_entity="PRO_LICENSE", supported_language="all",
                patterns=[Pattern("pro_license", r"\bLIC-\d{5}\b", 1.0)],
            ),
            PatternRecognizer(
                supported_entity="HEALTH_ID", supported_language="all",
                patterns=[Pattern("health_id", r"\b\d{3} \d{3} \d{4}\b", 1.0)],
            ),
            PatternRecognizer(
                supported_entity="DRIVER_LICENSE", supported_language="all",
                patterns=[Pattern("driver_license", r"\bD\d{7}\b", 1.0)],
            ),
            PatternRecognizer(
                supported_entity="VOTER_ID", supported_language="all",
                patterns=[Pattern("voter_id", r"\bV\d{7}\b", 1.0)],
            ),
            PatternRecognizer(
                supported_entity="RESIDENCE_PERMIT", supported_language="all",
                patterns=[Pattern("residence_permit", r"\bRP\d{6}\b", 1.0)],
            ),
            PatternRecognizer(
                supported_entity="MEETING_ID", supported_language="all",
                patterns=[Pattern("meeting_id", r"\b\d{3} \d{3} \d{3}\b", 1.0)],
            ),
            PatternRecognizer(
                supported_entity="GEO_COORDINATES", supported_language="all",
                patterns=[Pattern("geo_coordinates", r"\b\d{1,3}\.\d{4}, \d{1,3}\.\d{4}\b", 1.0)],
            ),
            PatternRecognizer(
                supported_entity="FAX_NUMBER", supported_language="all",
                patterns=[Pattern("fax", r"\b\+?\d{1,3} \d{2,4} \d{4,}\b", 1.0)],
            ),
            PatternRecognizer(
                supported_entity="BENEFIT_ID", supported_language="all",
                patterns=[Pattern("benefit_id", r"\bB\d{8}\b", 1.0)],
            ),
            PatternRecognizer(
                supported_entity="MILITARY_ID", supported_language="all",
                patterns=[Pattern("military_id", r"\bM\d{8}\b", 1.0)],
            ),
            PatternRecognizer(
                supported_entity="DEVICE_ID", supported_language="all",
                patterns=[Pattern("device_id", r"\bDEV-\d{9}\b", 1.05)],
            ),
        ]

        for rec in [
            self.address_recognizer, self.phone_recognizer, self.date_recognizer,
            self.passport_recognizer, self.id_recognizer, self.ip_recognizer,
            self.mac_recognizer, self.imei_recognizer,
            self.health_recognizer, self.plate_recognizer
        ] + additional_recognizers:
            self.analyzer.registry.add_recognizer(rec)

        # Note: CREDIT_CARD and BANK_ACCOUNT are validated via custom injections
        # (Luhn / IBAN checks) in _inject_custom_matches to avoid high-recall base-regex false positives.

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
        # DO NOT allow digits inside a person name
        if any(ch.isdigit() for ch in span):
            return False

        # Reject UUID/GUID patterns
        if re.fullmatch(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}", span):
            return False

        # Reject alphanumeric codes (MIT-2024-778899, RP333444, EMP-12345, etc.)
        if re.fullmatch(r"[A-Za-z]{1,5}-?\d{3,}", span):
            return False

        # Reject 100% uppercase tokens
        if span.isupper():
            return False

        # Reject tokens that look like OTP / PIN
        if re.fullmatch(r"\d{4,10}", span):
            return False      
        
        if re.search(r"\b(mail|e-mail|email|correo|e-?posta|adresse|address|telefon|phone|tel)\b", s, re.I):
            return False
       
        if re.search(r"\b(appelle|numero|nummer|número|policy|license|licence|kontonummer|passeport|passport)\b", s, re.I):
            return False
       
        if re.match(r"^\s*(?:je\s+m['’]|j['’]|je m['’])", s.lower()):
            return False

        tokens = [t for t in re.split(r"\s+", s) if t]
        low = [re.sub(r"^\W+|\W+$", "", t.lower()) for t in tokens]
        # If an intro cue precedes this span, prefer PERSON even if the first token looks like a street word


        if self._has_intro_prefix(text, start):
            # do not accept if tokens contain identity/tax/passport labels
            label_guard = ({kw.lower() for kw in self.ID_KEYWORDS}
                        | {kw.lower() for kw in self.TAX_KEYWORDS}
                        | {kw.lower() for kw in self.PASSPORT_KEYWORDS}
                        | {"nummer", "nummern", "ausweisnummer", "personalausweisnummer"})
            if any(tok in self.PERSON_BLACKLIST_WORDS or tok in label_guard for tok in low):
                pass  # fall through to normal checks (reject below)
            else:
                # accept only if intro is very close and same sentence (no prior .?!)
                left_ctx = text[max(0, start - 40):start]
                if any(cue in left_ctx.lower() for cue in self.INTRO_CUES):
                    punct_break = re.search(r"[\.!?]", left_ctx)
                    if not punct_break or punct_break.end() < len(left_ctx) - 20:
                        if tokens and low[-1] not in self.STREET_BLOCKERS \
                        and any(re.match(r"^[A-Za-zÀ-ÖØ-öø-ÿĀ-ſ]", t) and re.match(r"^[A-ZÀ-ÖØ-ÝÄÖÜ]", t) for t in tokens):
                            return True        
        

        if re.search(r"(?i)\bich\s+bin\s*$", text[max(0, start - 12):start]):
            right = text[start:min(len(text), start + 20)].lower()
            if re.match(r"(und|habe|hab|heute|sehr|einfach|beschäftigt|gemacht)\b", right):
                return False

        if "gasse" in low or "koordinaten" in low:
            return False
        if any(tok in self.PERSON_BLACKLIST_WORDS for tok in low):
            return False
        if all(tok in self.STREET_BLOCKERS for tok in low):
            return False
        if any(tok in self.NON_PERSON_SINGLE_TOKENS for tok in low):
            return False
        if len(tokens) > 1:
            # Require at least one capitalized Latin token among tokens that start with a letter
            latin_tokens = [t for t in tokens if re.match(r"^[A-Za-zÀ-ÖØ-öø-ÿĀ-ſ]", t)]
            # If there are Latin-script tokens, require at least one capitalized Latin token
            if latin_tokens and not any(t[0].isupper() for t in latin_tokens):
                return False

            # Reject obvious sentence fragments that start with pronouns/auxiliary verbs
            non_person_words = {
                "ich", "du", "er", "sie", "es", "wir", "ihr",
                "möchte", "kann", "werde", "würde", "habe", "bin", "ist", "sind", "hat",
                "für", "von", "zu", "auf", "bei", "mit", "ohne", "in", "das", "der", "die", "den", "dem",
            }
            if any(tok.lower() in non_person_words for tok in tokens[:2]):
                return False

            # Require tokens to look like a name in DE/EN when Latin-script tokens are present
            if latin_tokens:
                if not self._looks_like_name_de_en(tokens):
                    return False
                return True

            # For non-Latin scripts (e.g., Cyrillic, Greek, Arabic), be permissive:
            # accept multi-token spans where each token contains alphabetic characters
            # and tokens are not blacklisted or street-like.
            # This avoids over-relying on Latin capitalization heuristics.
            if all(any(ch.isalpha() for ch in t) for t in tokens):
                if any(tok in self.PERSON_BLACKLIST_WORDS for tok in low):
                    return False
                if all(tok in self.STREET_BLOCKERS for tok in low):
                    return False
                return True
            return False
        t0 = low[0]
        if t0 in self.PRONOUN_PERSONS:
            return False

        # Single-token names: be conservative — accept only when preceded by an intro cue or a title
        if len(tokens) == 1:
            # Special case: accept lowercase name-like tokens after "ich bin" if clause boundary follows
            ich_bin_left = re.search(r"(?i)\bich\s+bin\s*$", text[max(0, start - 12):start])
            if ich_bin_left:
                tok = tokens[0]
                right = text[start:min(len(text), start + 24)]
                end_ok = bool(re.match(r"\s*(?:[\.,;:!?]\s*|$)", right))
                if end_ok and self._looks_like_name_token(tok):
                    return True
                # If it's not name-like (or followed by more sentence), it's NOT a person
                return False

            # Accept if clearly introduced ("my name is Anna")
            if self._has_intro_prefix(text, start):
                return True
            # Accept if immediately preceded by a title (Herr/Frau/Dr/Mr/etc.)
            left = text[max(0, start - 40):start]
            if re.search(r"\b(?:" + "|".join(re.escape(t) for t in self.TITLE_TOKENS) + r")\b\s*$", left, re.I):
                return True
            return False
        
        
        # 🚫 single-token near street word? Drop
        left_ctx = text[max(0, start - 24):start].lower()
        prefix = text[max(0, start - 40):start].lower()
        # If there is an intro cue immediately before the span, allow PERSON even if it contains a street token
        if any(sb in left_ctx for sb in self.STREET_BLOCKERS) and not any(cue in prefix for cue in self.INTRO_CUES):
            return False

        # 
        # intro cue check (if present, we'll accept a person span)
        # BUT: only if the span is close to the intro cue (within ~20 chars) to avoid false positives
        # where an intro cue appears much earlier but is followed by unrelated text
        if any(cue in prefix for cue in self.INTRO_CUES):
            # Check if the intro cue is CLOSE (recent) - within last 20 characters
            # This filters out cases like "mein name ist Frank Verz, [20+ chars later] Gewerbe"
            close_prefix = text[max(0, start - 20):start].lower()
            if any(cue in close_prefix for cue in self.INTRO_CUES):
                # Intro cue is very close, likely directly connected to this span - accept it
                return True
            else:
                # Intro cue is 20-40 chars back - too far to reliably apply to this span
                # For multi-token spans, be extra conservative and don't accept
                if len(tokens) > 1:
                    # Check for context-breaking words that confirm this isn't a name
                    intervening = text[max(0, start - 40):start + 15].lower()
                    context_breakers = {
                        "möchte", "kann", "werde", "würde", "habe", "hab", "bin", "ist", "sind", "hat", "had", "have",
                        "für", "von", "zu", "zum", "zur", "auf", "bei", "mit", "ohne",
                        "anmelden", "anmeldung", "anfrage", "anfragen", "dienst", "dienste",
                        "ein", "eine", "einer", "einem", "einen",
                    }
                    if any(word in intervening for word in context_breakers):
                        return False
                    # Even without explicit context breakers, don't trust far-away intro cues for multi-token spans
                    return False
        if re.match(r"^[A-Za-zÀ-ÖØ-öø-ÿĀ-ſ]", tokens[0]) and not tokens[0][0].isupper():
            return False
        return True

    def _looks_like_name_de_en(self, tokens: list) -> bool:
        """Heuristic: return True if tokens plausibly form a personal name in DE/EN.
        - At least one token starts with a capital letter (for Latin scripts)
        - No digits present
        - Tokens are not street blockers or single-token non-person tokens
        """
        if not tokens:
            return False
        # no digits
        if any(re.search(r"\d", t) for t in tokens):
            return False
        low = [t.lower() for t in tokens]
        # Avoid all-street/component tokens
        if all(tok in self.STREET_BLOCKERS for tok in low):
            return False
        # Avoid obvious non-person single tokens
        if any(tok in self.NON_PERSON_SINGLE_TOKENS for tok in low):
            return False
        # At least one capitalized token among letter-starting tokens
        for t in tokens:
            if re.match(r"^[A-Za-zÀ-ÖØ-öø-ÿĀ-ſ]", t) and t[0].isupper():
                return True
        return False

    def _inject_name_intro_persons(self, text, results):
        add = []
        for rx in self.INTRO_PATTERNS:
            for m in rx.finditer(text):
                s, e = m.start(1), m.end(1)
                span = text[s:e]
                if self._plausible_person(span, text, s):
                    add.append(RecognizerResult("PERSON", s, e, 0.96))
        return self._resolve_overlaps(text, results + add) if add else results

    def _has_intro_prefix(self, text: str, start: int, window: int = 48) -> bool:
        """Heuristic: is there an intro cue immediately before this span?"""
        prefix = text[max(0, start - window):start].lower()
        return any(cue in prefix for cue in self.INTRO_CUES)
    
    def _looks_like_name_token(self, token: str) -> bool:
            """
            Single-token name-likeness check used for the special 'ich bin <token>' case.
            """
            if not token:
                return False
            t = token.strip()
            if not re.fullmatch(r"[A-Za-zÀ-ÖØ-öø-ÿĀ-ſ][A-Za-zÀ-ÖØ-öø-ÿĀ-ſ'’-]*", t):
                return False
            if len(t) < 2:
                return False
            low = t.lower()
            if low in self.STREET_BLOCKERS \
            or low in self.NON_PERSON_SINGLE_TOKENS \
            or low in self.PERSON_BLACKLIST_WORDS \
            or low in getattr(self, 'DE_NON_NAME_AFTER_ICH_BIN', set()):
                return False
            return True
    

    def _effective_priority(self, text: str, r) -> int:
        """Bump PERSON priority above ADDRESS if preceded by an intro cue."""
        base = self.PRIORITY.get(r.entity_type, 1)
        if r.entity_type == "PERSON":
            if self._has_intro_prefix(text, r.start):
                # Make PERSON outrank ADDRESS (8) when intro precedes the span
                return max(base, 9)
        return base
    
    # ====================
    # Overlaps / filters
    # ====================
    def _resolve_overlaps(self, text, items):
        # Sort by score desc, priority desc, span length desc so stronger/higher-priority
        # recognizers are considered first.
        items = sorted(
            items,
            key=lambda r: (
                -r.score,
                -self.PRIORITY.get(r.entity_type, 1),
                -(r.end - r.start),
            ),
        )
        kept = []
        for r in items:
            conflict = False
            for k in list(kept):
                if not (r.end <= k.start or r.start >= k.end):
                    pr = self._effective_priority(text, r)
                    pk = self._effective_priority(text, k)

                    # Special-case: prefer PHONE_NUMBER over FAX_NUMBER unless 'fax' explicitly appears near the span
                    if {r.entity_type, k.entity_type} == {"FAX_NUMBER", "PHONE_NUMBER"}:
                        # Check for explicit 'fax' token in a small neighborhood
                        left = text[max(0, min(r.start, k.start) - 24):min(r.start, k.start)].lower()
                        right = text[max(r.end, k.end):min(len(text), max(r.end, k.end) + 24)].lower()
                        if ("fax" in left) or ("fax" in right):
                            # Let standard scoring/priority decide when an explicit 'fax' label exists
                            pass
                        else:
                            # Prefer PHONE_NUMBER (drop FAX)
                            if r.entity_type == "FAX_NUMBER":
                                # existing kept item wins (we drop r)
                                conflict = True
                                break
                            else:
                                # r is PHONE_NUMBER and should replace k (FAX)
                                try:
                                    kept.remove(k)
                                except ValueError:
                                    pass
                                kept.append(r)
                                conflict = True
                                break

                    # If r has strictly higher score or higher effective priority, replace k
                    if (r.score > k.score) or (r.score == k.score and pr > pk) or (
                        r.score == k.score and pr == pk and (r.end - r.start) > (k.end - k.start)
                    ):
                        # remove k and keep r (r is stronger)
                        try:
                            kept.remove(k)
                        except ValueError:
                            pass
                        kept.append(r)
                        conflict = True
                        break
                    else:
                        # existing kept item wins -> drop r
                        conflict = True
                        break
            if not conflict:
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

    def _demote_phone_over_health_id(self, text, items):
        """Prevent NHS numbers (944 476 5919 format) from being detected as PHONE"""
        health_ids = [(r.start, r.end) for r in items if r.entity_type == "HEALTH_ID"]
        if not health_ids:
            return items
        out = []
        for r in items:
            if r.entity_type != "PHONE_NUMBER":
                out.append(r)
                continue
            # Skip PHONE if it overlaps with HEALTH_ID
            if any(not (r.end <= hs or r.start >= he) for hs, he in health_ids):
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



    
    def _filter_non_postal_locations(self, text: str, items, enable: bool = True, window: int = 16):
        """
        Drop LOCATION that:
        - does NOT match EU postal patterns
        - AND is NOT near an ADDRESS
        - AND IS near a PHONE or MEETING_ID (to weed out non‑EU postal formats)
        - OR is standalone (no digits)
        """
        if not enable or not items:
            return items

        out = []

        # Collect spans
        addr_spans = [(r.start, r.end) for r in items if r.entity_type == "ADDRESS"]
        phone_spans = [(r.start, r.end) for r in items if r.entity_type in ("PHONE_NUMBER", "MEETING_ID")]

        def spans_near(a, b):
            return abs(a[0] - b[1]) <= window or abs(a[1] - b[0]) <= window

        def near_any(loc_span, spans):
            for sp in spans:
                # overlapping
                if not (loc_span[1] <= sp[0] or loc_span[0] >= sp[1]):
                    return True
                # adjacent within window
                if spans_near(loc_span, sp):
                    return True
            return False

        for r in items:
            if r.entity_type != "LOCATION":
                out.append(r)
                continue

            loc_span = (r.start, r.end)
            span_text = text[r.start:r.end]

            # Drop LOCATION that look like apartment numbers
            if re.match(r"^\w+ \d+$", span_text):
                continue

            # Digit inside LOCATION span?
            has_digit = any(ch.isdigit() for ch in span_text)

            # Validate as EU postal?
            is_postal = False
            if has_digit:
                for patt in self.POSTAL_EU_PATTERNS:
                    if re.search(patt, span_text, flags=re.I | re.UNICODE):
                        is_postal = True
                        break

            # Keep LOCATION if EU postal (correct)
            if has_digit and is_postal:
                out.append(r)
                continue

            # Keep LOCATION if near ADDRESS (merged/adjacent street+postal)
            if near_any(loc_span, addr_spans):
                out.append(r)
                continue

            
            raw_segment_before_loc = text[max(0, r.start - 24):r.start]

            phone_like = re.search(r"\b\d[\d\s\-()]{5,}\d\b", raw_segment_before_loc)

            if phone_like and not has_digit and not is_postal:
                # Non‑EU postal formats: keep PHONE, drop city
                continue

            # Drop short LOCATIONs that look like apartment/unit numbers
            if re.match(r"^\w+ \d+$", span_text):
                continue

            if span_text and span_text[0].islower():
                continue


            if re.match(r"(?i)^(gibt|ist|sind|war|waren|kann|können|moechte|möchte|will|wird|werden|habe|hat|wie|wo|wer|was|wann)\\b", span_text):
                continue


            # ❗ DROP standalone LOCATION
            continue

        return out
    

    def _filter_locations_with_inline_or_near_labels(self, text: str, items, window: int = 28):
        
        """
        Drop LOCATION when ID/PASSPORT/TAX label keywords appear:
          • inside the LOCATION span (inline, as separate tokens), or
          • within `window` chars on either side (adjacent).
        Uses word-boundary style checks to avoid substrings like 'id' matching in 'Madrid'.
        """
        
        if not items:
            return items

        lt = text.lower()

        # Prepare a single boundary-aware regex for all label keywords.
        # We escape each keyword and join with alternation.
        # (?<!\\w) and (?!\\w) are word-boundary analogs for unicode-aware token edges.
        label_tokens_lower = (
            {kw.lower() for kw in self.PASSPORT_KEYWORDS}
            | {kw.lower() for kw in self.ID_KEYWORDS}
            | {kw.lower() for kw in self.TAX_KEYWORDS}
        )

        # Sort longer first to avoid partials like 'id' shadowing 'identity card'
        sorted_kws = sorted(label_tokens_lower, key=len, reverse=True)
        # Build a pattern that matches any keyword as a token/phrase with boundaries
        # e.g., (?<!\w)(passport|identity card|tax id|vat|ustid)(?!\w)
        kw_alt = "|".join(re.escape(kw) for kw in sorted_kws)
        kw_re = re.compile(rf"(?<!\w)(?:{kw_alt})(?!\w)")

        def contains_kw_token(hay: str) -> bool:
            return bool(kw_re.search(hay))

        out = []
        for r in items:
            if r.entity_type != "LOCATION":
                out.append(r)
                continue


        
            span_lower = lt[r.start:r.end]
            if contains_kw_token(span_lower):
                # Label keyword is inline (proper token) inside LOCATION → drop
                continue

            left = lt[max(0, r.start - window):r.start]
            right = lt[r.end:min(len(text), r.end + window)]
            # Normalize boundary punctuation/whitespace
            left_norm = re.sub(r"[\s:,\-–—\|]+$", " ", left)
            right_norm = re.sub(r"^[\s:,\-–—\|]+", " ", right)

            if contains_kw_token(left_norm) or contains_kw_token(right_norm):
                # Label keyword is adjacent (as a token) → drop
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
        label_stops = re.compile(r"(?i)\b(email|e-mail|mail|meine|la mia email|mon email|adresse|für|gründung|unternehmen)\b")
        multiline_addr = re.compile(r"(?i)(?:nr\.?|no\.?|number|nummer|num)\s*:?\s*\d|(?:plz\/ort|plz|postal|city|stadt|ort)", re.MULTILINE)
        out = []
        for r in items:
            if r.entity_type != "ADDRESS":
                out.append(r)
                continue
            s, e = r.start, r.end
            span = text[s:e]
            
            # Check if this is a multi-line address (has number or city labels on different lines)
            has_multiline = bool(multiline_addr.search(span))
            
            # Only trim at first newline if this is NOT a multi-line tagged address
            cut = -1
            if not has_multiline:
                cut = span.find("\n")
            
            if cut != -1:
                e = s + cut
            else:
                m = label_stops.search(span)
                if m:
                    e = s + m.start()
            trimmed = span[:e - s].rstrip(" .,:;–—")
            if trimmed:
                # Additional filter: DROP addresses that don't contain house numbers or street types that require numbers
                # E.g., "Tempelhof-Shöneberg" is just a district name, not a complete address
                # Valid addresses should have digits (house numbers) or be specific street patterns
                if not re.search(r"\d", trimmed):
                    # No digits - check if it's a district that got misdetected
                    # If it doesn't contain typical address markers, skip it
                    addr_markers = r"(?i)\b(straße|strasse|str\.?|street|avenue|avenue|weg|platz|gasse|ring|allée|allee)"
                    if not re.search(addr_markers, trimmed):
                        # No street type patterns either - likely just a location name, not a residential address
                        continue
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

    def _span_inside_email(self, text: str, s: int, e: int) -> bool:
        """Return True if the span [s,e) is fully contained within an email address in the text."""
        for m in re.finditer(r"[\w\.\-+%]+@[\w\.\-]+\.[A-Za-z]{2,}", text):
            if m.start() <= s and m.end() >= e:
                return True
        return False

    def _promote_phone_to_account_if_labeled(self, text: str, items):
        """Promote PHONE_NUMBER spans to ACCOUNT_NUMBER when immediately preceded by a bank/account label.
        This handles cases like 'Kontonummer: 1234-567890-12' where the labeled numeric should be an account.
        """
        out = []
        bank_label_rx = re.compile(r"\b(?:iban|bic|swift|account(?:\s*no\.? )?|acct|acct\.?|konto(?:nummer)?|kontonr|kontonummer|bank|konto|rib|bban)\b", re.I)
        for r in items:
            if r.entity_type == 'PHONE_NUMBER':
                left = text[max(0, r.start - 28):r.start].lower()
                if bank_label_rx.search(left):
                    digits = re.sub(r"\D", "", text[r.start:r.end])
                    if len(digits) >= 6:
                        out.append(RecognizerResult('ACCOUNT_NUMBER', r.start, r.end, 1.05))
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

    def _looks_like_api_key(self, token: str) -> bool:
        """Generic unseen-provider API key detector."""
        if len(token) < 28:
            return False

        # reject UUID (big false positive)
        if re.fullmatch(
            r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-"
            r"[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
            r"[0-9a-fA-F]{12}", token
        ):
            return False

        # reject natural-language‑ish strings
        if re.search(r"[aeiouAEIOU]", token) and len(set(token)) < len(token) * 0.6:
            return False

        # entropy score
        p = {c: token.count(c) / len(token) for c in set(token)}
        entropy = -sum(v * math.log2(v) for v in p.values())

        return entropy >= 3.2

    # ====================
    # CUSTOM INJECTIONS
    # ====================
    def _inject_custom_matches(self, text, results):
        add = []

        # Precompute validated IBAN/BIC spans so other detectors (e.g., CREDIT_CARD) won't hijack parts
        validated_iban_spans = []
        for m in self.IBAN_RX.finditer(text):
            try:
                if self._iban_ok(m.group()):
                    validated_iban_spans.append((m.start(), m.end()))
            except Exception:
                pass
        validated_bic_spans = []
        for m in self.BIC_RX.finditer(text):
            try:
                if m.group(2) in self.ISO_COUNTRIES:
                    validated_bic_spans.append((m.start(), m.end()))
            except Exception:
                pass

        # Emails — inject early so other matches can't replace parts of addresses/domains
        for m in self.EMAIL_RX.finditer(text):
            add.append(RecognizerResult("EMAIL_ADDRESS", m.start(), m.end(), 1.0))

        # ============================================================
        # EARLY API KEY DETECTION — PROVIDER KEYS + api_key=
        # (Runs before ID/PHONE/MAC shredding – critical!)
        # ============================================================

        # --- Provider patterns (AWS, GitHub, OpenAI, Cloudflare, Slack…) ---
        for rx, name in self.API_KEY_PROVIDER_RXS:
            for m in rx.finditer(text):
                s, e = m.start(), m.end()
                # Use capturing groups if available
                if m.lastindex:
                    s, e = m.start(1), m.end(1)
                add.append(RecognizerResult("API_KEY", s, e, 1.20))

        # --- Provider-specific labeled patterns (more targeted) ---
        # Slack labeled patterns
        for m in re.finditer(r"(?i)\bslack[_\s-]*(?:api_?)?token\s*[:=]\s*([A-Za-z0-9_\-]{12,})", text):
            s, e = m.start(1), m.end(1)
            add.append(RecognizerResult("API_KEY", s, e, 1.19))
        
        # Stripe labeled patterns
        for m in re.finditer(r"(?i)(?:stripe[_\s-]*)?(?:secret|public)[_\s-]*key\s*[:=]\s*([a-z0-9_]{16,})", text):
            s, e = m.start(1), m.end(1)
            add.append(RecognizerResult("API_KEY", s, e, 1.19))
        
        # Cloudflare labeled patterns
        for m in re.finditer(r"(?i)\bcloudflare[_\s-]*(?:api_?)?token\s*[:=]\s*([a-z0-9]{32,})", text):
            s, e = m.start(1), m.end(1)
            add.append(RecognizerResult("API_KEY", s, e, 1.19))
        
        # Generic labeled api_key= (lower priority to avoid false positives)
        for m in re.finditer(
            r"(?i)\b(?:google|azure|github|sendgrid|mailchimp|twilio|digitalocean|firebase|openai|stripe|aws)[_\s-]*(?:api[_-]?)?key\s*[:=]\s*([A-Za-z0-9._\-+/=]{12,})",
            text,
        ):
            s, e = m.start(1), m.end(1)
            add.append(RecognizerResult("API_KEY", s, e, 1.18))
    
        # ============================================================
        # SESSION_ID, ACCESS_TOKEN, REFRESH_TOKEN, ACCESS_CODE, OTP_CODE — inject early with high scores
        for rx, ent_name in self.TOKEN_RXS:
            for m in rx.finditer(text):
                s, e = (m.start(1), m.end(1)) if m.lastindex else (m.start(), m.end())
                token_val = text[s:e].strip()
                if len(token_val) >= 4:  # Minimum length for tokens/codes
                    # Check specific patterns first (before generic "code")
                    if "otp" in ent_name.lower() or "mfa" in ent_name.lower() or "verification" in ent_name.lower():
                        add.append(RecognizerResult("OTP_CODE", s, e, 1.03))
                    elif "session" in ent_name.lower() or "sid" in ent_name.lower():
                        add.append(RecognizerResult("SESSION_ID", s, e, 1.04))
                    elif "refresh" in ent_name.lower():
                        add.append(RecognizerResult("REFRESH_TOKEN", s, e, 1.04))
                    elif "access_token" in ent_name.lower() or "bearer" in ent_name.lower():
                        add.append(RecognizerResult("ACCESS_TOKEN", s, e, 1.04))
                    elif "access_code" in ent_name.lower() or "pin" in ent_name.lower() or (ent_name.lower() == "code_labeled"):
                        add.append(RecognizerResult("ACCESS_CODE", s, e, 1.03))
                    elif "token" in ent_name.lower():
                        add.append(RecognizerResult("ACCESS_TOKEN", s, e, 1.04))

        # ============================================= #
        # API KEY DETECTION                             #
        # ============================================= #
        # entropy fallback — AFTER token detectors only #
        #---------------------------------------------- #

        for m in re.finditer(r"\b[A-Za-z0-9._\-+/=]{28,}\b", text):
            token = m.group(0)

            # Do not override tokens
            if any(
                r.entity_type in (
                    "SESSION_ID",
                    "ACCESS_TOKEN",
                    "REFRESH_TOKEN",
                    "ACCESS_CODE",
                    "OTP_CODE",
                )
                and not (m.end() <= r.start or m.start() >= r.end)
                for r in add
            ):
                continue

            if self._looks_like_api_key(token):
                add.append(RecognizerResult("API_KEY", m.start(), m.end(), 1.05))

        # ----- Stripe public/secret → Stay as API_KEY (not converting to PAYMENT_TOKEN) -----
        # Stripe and OpenAI keys are now classified and kept as API_KEY for consistency
        # This allows tests to properly detect them as <API_KEY>
        # Users can differentiate by context or use additional flags if needed


                 

        # Reference/Tracking Identifiers — business/legal/government context (inject after CASE_REFERENCE)
        # FILE_NUMBER: Labeled file identifiers
        for m in self.FILE_NUMBER_RX.finditer(text):
            s, e = m.start(), m.end()
            add.append(RecognizerResult("FILE_NUMBER", s, e, 1.00))

        # TRANSACTION_NUMBER: Labeled transaction identifiers
        for m in self.TRANSACTION_NUMBER_RX.finditer(text):
            s, e = m.start(), m.end()
            add.append(RecognizerResult("TRANSACTION_NUMBER", s, e, 1.00))

        # CUSTOMER_NUMBER: Labeled customer identifiers
        for m in self.CUSTOMER_NUMBER_RX.finditer(text):
            s, e = m.start(), m.end()
            add.append(RecognizerResult("CUSTOMER_NUMBER", s, e, 0.99))

        # TICKET_ID: Labeled ticket/case identifiers
        for m in self.TICKET_ID_RX.finditer(text):
            s, e = m.start(), m.end()
            add.append(RecognizerResult("TICKET_ID", s, e, 0.99))

        # Addresses
        for m in self.STRICT_ADDRESS_RX.finditer(text):
            s, e = m.start(), m.end()
            span = m.group()
            # Do not let strict-address matches that overlap an email beat email matches
            if any(not (e <= a.start or s >= a.end) for a in add if a.entity_type in ("EMAIL", "EMAIL_ADDRESS")):
                continue
            # If an intro cue immediately precedes this span (e.g., "Je m'appelle Rue Victor"),
            # prefer PERSON and skip injecting an ADDRESS so the intro-based PERSON can win.
            # Consider a small right-context as intro cues may overlap the match start
            prefix = text[max(0, s - 48):s + 16].lower()
            if any(cue in prefix for cue in self.INTRO_CUES):
                continue
            # Guard against matching education/employment IDs as addresses (e.g., "student ID is STU-12345"
            # where "student" contains "tal" which is a street suffix in German).
            # Check the broader context to see if this is actually an ID label
            broader_span = text[max(0, s - 50):e + 10].lower()
            if any(label in broader_span for label in ["student id", "student number", "studentenausweis",
                                                       "employee id", "employee number",
                                                       "professional license", "license number",
                                                       "pro license", "credential"]):
                continue
            # Conservative guard: require either a house number or an explicit street suffix to reduce city-name false positives
            if not re.search(r"\d", span):
                # If no digit present but a street suffix exists, try to absorb a following house-number from the right context
                right = text[e:e+16]
                mnum = re.match(r"^\s*[,:]?\s*(\d{1,4}[A-Za-z]?(?:\s*[-–]\s*\d+[A-Za-z]?)?)", right)
                if mnum:
                    # Expand match to include the house number
                    e = e + mnum.end()
                    span = text[s:e]
                else:
                    # street suffix check (use existing compound suffix regex)
                    if not re.search(self.STREET_SUFFIX_COMPOUND, span, flags=re.I | re.UNICODE):
                        continue
            # Give strict-address matches a slightly higher score so they win numeric overlaps (house+postal)
            add.append(RecognizerResult("ADDRESS", s, e, 1.02))

        # Fallback street+number detection (conservative)
        for m in self.FALLBACK_STREET_RX.finditer(text):
            s, e = m.start(), m.end()
            # Do not let fallback-address match overlap an email
            if any(not (e <= a.start or s >= a.end) for a in add if a.entity_type in ("EMAIL", "EMAIL_ADDRESS")):
                continue
            # If an intro cue immediately precedes this span, prefer PERSON and skip injecting ADDRESS
            # Consider small right-context so intro cues that overlap the match cancel ADDRESS injection
            prefix = text[max(0, s - 48):s + 16].lower()
            if any(cue in prefix for cue in self.INTRO_CUES):
                continue
            # Avoid duplicate ADDRESS injections
            if any(not (e <= a.start or s >= a.end) for a in add if a.entity_type == "ADDRESS"):
                continue
            add.append(RecognizerResult("ADDRESS", s, e, 1.01))

        # Postal → LOCATION
        for patt in self.POSTAL_EU_PATTERNS:
            for m in re.finditer(patt, text, flags=re.I | re.UNICODE):
                s, e = m.start(), m.end()
                matched = m.group()
                # Skip matches that are a tail after a digit (avoid partial matches like '-000 São Paulo')
                if s > 0 and text[s-1].isdigit():
                    continue
                # Avoid accidental matches on lowercase language words followed by short numbers (e.g., 'est 06')
                alpha = re.match(r"\s*([A-Za-zÀ-ÖØ-öø-ÿ]+)", matched)
                if alpha and alpha.group(1).islower():
                    continue
                add.append(RecognizerResult("LOCATION", s, e, 0.92))
        # Phones or Meeting IDs
        for m in self.PHONE_RX.finditer(text):
            s, e = m.start(), m.end()
            left = text[max(0, s - 24):s].lower()
            right = text[e:min(len(text), e + 24)].lower()
            # If fax appears near the number on either side, skip phone to let FAX handling win
            if "fax" in left or "fax" in right:
                continue
            if "meeting" in left or "meeting" in right:
                # Meeting IDs should beat other heuristics when labeled (broad match)
                add.append(RecognizerResult("MEETING_ID", s, e, 1.05))
            else:
                digits = re.sub(r"\D", "", m.group())
                if len(digits) >= 7:
                    # Avoid tagging address/postal fragments as PHONEs: if street-like tokens are near the number
                    # or if a postal-like number begins immediately to the right, skip treating as PHONE
                    left_ctx = left
                    right_ctx = right
                    if any(sb in left_ctx for sb in self.STREET_BLOCKERS) or any(sb in right_ctx for sb in self.STREET_BLOCKERS):
                        continue
                    # If right context starts with a postal-like fragment (e.g., '- 10115' or ' 10115'), skip
                    if re.match(r"^\s*[-–]?\s*\d{3,6}\b", right_ctx):
                        continue
                    # If ID-like label tokens appear near the number, this is more likely an ID than a phone
                    if any(k in left or k in right for k in self.ID_KEYWORDS):
                        continue
                    add.append(RecognizerResult("PHONE_NUMBER", s, e, 0.90))
        
        # Combine labeled multi-line address fragments into ADDRESS when possible
        # e.g. "Straße: Hauptstraße\nNr.: 10\nPLZ/Ort: 10115 Berlin" or
        # "Street: Baker St.\nNumber: 221B\nCity: London"
        locs = [r for r in add if r.entity_type == "LOCATION"]
        for loc in locs:
            # find the newline that starts the LOCATION line
            loc_line_start = text.rfind("\n", 0, loc.start)
            if loc_line_start == -1:
                continue
            # previous line (likely number label)
            prev_line_end = loc_line_start
            prev_line_start = text.rfind("\n", 0, prev_line_end - 1)
            prev_line = text[prev_line_start + 1:prev_line_end].strip() if prev_line_start != -1 else text[:prev_line_end].strip()
            # line above that (likely street label)
            prev2_end = prev_line_start
            if prev2_end == -1:
                continue
            prev2_start = text.rfind("\n", 0, prev2_end - 1)
            prev2_line = text[prev2_start + 1:prev2_end].strip() if prev2_start != -1 else text[:prev2_end].strip()

            low2 = prev2_line.lower()
            low1 = prev_line.lower()
            # street label detection — use substring checks to tolerate punctuation like ':'
            if not any(k in low2 for k in ("straße", "strasse", "str.", "street", "st.")):
                continue
            # number label detection — tolerate 'Nr', 'No', 'Number', 'Nr.' etc.
            if not any(k in low1 for k in ("nr", "no", "number", "nummer", "num")):
                continue
            # Anchor near first capitalized token in street line
            mname = re.search(r"[A-ZÀ-ÖØ-ÝÄÖÜ][\w'’\.-]+", prev2_line)
            if not mname:
                continue
            s = prev2_start + 1 + mname.start()
            e = loc.end
            # If an overlapping ADDRESS exists, prefer expanding smaller spans to the larger merged span
            overlaps = [a for a in add if a.entity_type == "ADDRESS" and not (e <= a.start or s >= a.end)]
            if overlaps:
                expanded = False
                for a in overlaps:
                    # if the new span fully contains an existing smaller ADDRESS, replace it with the expanded span
                    if s <= a.start and e >= a.end:
                        try:
                            add.remove(a)
                        except ValueError:
                            pass
                        add.append(RecognizerResult("ADDRESS", s, e, max(a.score, 1.03)))
                        expanded = True
                        break
                if not expanded:
                    # otherwise keep existing address(es)
                    continue
            else:
                add.append(RecognizerResult("ADDRESS", s, e, 1.03))
        # Also detect fully labeled 3-line address blocks (street + number + city) even when no postal code was matched
        # Pattern matches: street_label:value\nnumber_label:value\ncity_label:value
        # Requires labels to be followed by colon or whitespace (to avoid matching "St." as a label when it's part of an address value)
        block_rx = re.compile(
            r"(?im)"
            r"(?:straße|strasse|str|street|adresse|address|rue)(?:\.|:|\s)(?:\s*:?\s*)([^\n:]+)"
            r"(?:\n\s*(?:nr|no|number|nummer|num)(?:\.|:|\s)(?:\s*:?\s*)([^\n:]+))?"
            r"(?:\n\s*(?:plz(?:/ort)?|postal|city|stadt|ort|ville|ciudad)(?:\.|:|\s)(?:\s*:?\s*)([^\n:]+))?"
        )
        
        _debug_block = False  # "Straße: Hauptstraße" in text and "Nr.:" in text
        if _debug_block:
            print(f"[DEBUG] block_rx processing. Current add list has {len(add)} entities:")
            for i, ent in enumerate(add):
                print(f"  [{i}] {ent.entity_type:15s} ({ent.start:3d}, {ent.end:3d}): {repr(text[ent.start:min(ent.end,ent.start+30)])}")
        
        for m in block_rx.finditer(text):
            # Extract the matched groups
            street_val = m.group(1)
            number_val = m.group(2)
            city_val = m.group(3)
            
            # Both number and city must be present for a valid address block
            if not (number_val and city_val):
                continue
            
            _debug_block2 = False  # "Straße: Hauptstraße" in text and "Nr.:" in text
            if _debug_block2:
                print(f"\n[DEBUG] block_rx matched! Groups: street={street_val!r}, number={number_val!r}, city={city_val!r}")
            
            s = m.start(1)
            # Calculate the end position: use the furthest non-None group's end
            if m.group(3):
                e = m.end(3)
            elif m.group(2):
                e = m.end(2)
            else:
                e = m.end(1)
            
            if _debug_block2:
                print(f"[DEBUG] Creating ADDRESS span: ({s}, {e}) = {repr(text[s:e][:50])}")
            
            overlaps = [a for a in add if a.entity_type == "ADDRESS" and not (e <= a.start or s >= a.end)]
            if _debug_block2:
                print(f"[DEBUG] Found {len(overlaps)} overlapping ADDRESS entities")
                for ov in overlaps:
                    print(f"  Overlap: ({ov.start}, {ov.end})")
                    print(f"    Condition 1 (contains): {s <= ov.start and e >= ov.end}")
                    print(f"    Condition 2 (overlap_start): {s <= ov.start and e > ov.start}")
                    print(f"    Condition 3 (overlap_end): {s < ov.end and e >= ov.end}")
                    print(f"    Width comparison: new={e-s}, old={ov.end - ov.start}, new_wider={e > ov.end - ov.start}")
            
            if overlaps:
                expanded = False
                for a in overlaps:
                    # If the new merged span fully contains an existing ADDRESS, or overlaps significantly, expand
                    if (s <= a.start and e >= a.end) or (s <= a.start and e > a.start) or (s < a.end and e >= a.end):
                        if _debug_block2:
                            print(f"[DEBUG] Merging: old=({a.start}, {a.end}), new=({s}, {e})")
                        try:
                            add.remove(a)
                        except ValueError:
                            pass
                        # Create a new span that covers both the old and new extents
                        new_s = min(s, a.start)
                        new_e = max(e, a.end)
                        add.append(RecognizerResult("ADDRESS", new_s, new_e, max(a.score, 1.03)))
                        expanded = True
                        break
                if not expanded:
                    # If there's an overlap but can't merge, prefer the larger new span over the smaller old one
                    for a in overlaps:
                        if e > a.end - a.start:  # New span is wider than old span
                            if _debug_block2:
                                print(f"[DEBUG] Replacing smaller old with new: new=({s}, {e}), old=({a.start}, {a.end})")
                            try:
                                add.remove(a)
                            except ValueError:
                                pass
                            add.append(RecognizerResult("ADDRESS", s, e, max(a.score, 1.03)))
                            expanded = True
                            break
                if not expanded:
                    if _debug_block2:
                        print(f"[DEBUG] NO expansion happened, skipping new ADDRESS")
                    continue
            else:
                if _debug_block2:
                    print(f"[DEBUG] No overlaps, adding ADDRESS ({s}, {e}) directly")
                add.append(RecognizerResult("ADDRESS", s, e, 1.03))

        # Fax (label-led)
        for fax in self.FAX_LABEL_RX.finditer(text):
            start = fax.end()
            seg = text[start:start + 64]
            m = re.search(r"(?:\+?\d{1,3}[ \-]?)?(?:\(?\d{1,4}\)?[ \-]?)?(?:\d[ \-]?){5,12}\d", seg)
            if m:
                s = start + m.start()
                e = start + m.end()
                add.append(RecognizerResult("FAX_NUMBER", s, e, 1.05))

        # Dates
        for patt in (self.DATE_REGEX_1, self.DATE_REGEX_2, self.DATE_REGEX_3, self.DATE_REGEX_4, self.DATE_REGEX_5):
            for m in re.finditer(patt, text, flags=re.I | re.UNICODE):
                add.append(RecognizerResult("DATE", m.start(), m.end(), 0.93))
        # Filter out common relative date words (e.g., 'today') which are not PII in noisy text
        RELATIVE_DATE_WORDS = {"today","yesterday","tomorrow","tonight","this morning","this afternoon","this evening"}
        add = [r for r in add if not (r.entity_type in ("DATE",) and text[r.start:r.end].strip().lower() in RELATIVE_DATE_WORDS)]

        # IDs
        for patt, _name in self.ID_PATTERNS:
            for m in re.finditer(patt, text, flags=re.I | re.UNICODE):
                s, e = (m.start(1), m.end(1)) if m.lastindex else (m.start(), m.end())
                left = text[max(0, s - 24):s].lower()
                # If the left context indicates this is an account/routing number, skip generic ID injection
                is_account_label = any(k in left for k in self.ACCOUNT_LABELS)
                if is_account_label:
                    continue
                # If ID label cues appear immediately to the left, boost the score so labeled IDs beat PHONE
                is_labeled = any(k in left for k in self.ID_KEYWORDS)
                score = 1.03 if is_labeled else 0.92
                # Map specific ID formats to more precise entities when known (e.g., German Personalausweis -> PASSPORT)
                ent_type = "PASSPORT" if "personalausweis" in _name.lower() else "ID_NUMBER"
                add.append(RecognizerResult(ent_type, s, e, score))

        # TAX strict - boost labeled priority
        for patt, _name in self.TAX_PATTERNS_STRICT:
            for m in re.finditer(patt, text, flags=re.I | re.UNICODE):
                s, e = (m.start(1), m.end(1)) if m.lastindex else (m.start(), m.end())
                left = text[max(0, m.start() - 24):m.start()].lower()
                is_labeled = any(k in left for k in ["steuer", "tax id", "tin", "vat"])
                score = 1.0 if is_labeled else 0.92
                add.append(RecognizerResult("TAX_ID", s, e, score))

        # EORI explicit labeled matches (prefer EORI when label present)
        for m in self.EORI_RX.finditer(text):
            s, e = (m.start(1), m.end(1)) if m.lastindex else (m.start(), m.end())
            # Prefer EORI as distinct entity (higher than generic TAX_ID)
            add.append(RecognizerResult("EORI", s, e, 1.03))

        # Commercial Register / Handelsregister — multilingual European support
        for m in self.COMMERCIAL_REGISTER_RX.finditer(text):
            s, e = m.start(), m.end()
            # High score to ensure commercial register captures are not misclassified
            add.append(RecognizerResult("COMMERCIAL_REGISTER", s, e, 1.04))

        # Case Reference / Case ID / Reference Number — multilingual support
        for m in self.CASE_REFERENCE_RX.finditer(text):
            s, e = m.start(), m.end()
            # Score 1.02 to win overlaps with PHONE (0.90) and DATE (0.93)
            add.append(RecognizerResult("CASE_REFERENCE", s, e, 1.02))

        # Labeled customer name — capture 'Customer Name: John Smith' patterns
        for m in re.finditer(r"(?i)\bcustomer\s+name\s*[:#\-]\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})", text):
            s, e = m.start(1), m.end(1)
            add.append(RecognizerResult("PERSON", s, e, 1.01))

        # German e-government identifiers
        # BundID: German Federal Digital Identity
        for m in self.BUND_ID_RX.finditer(text):
            s, e = m.start(), m.end()
            add.append(RecognizerResult("BUND_ID", s, e, 1.05))

        # ELSTER_ID: German tax authority login system (Elektronische Steuererklärung)
        for m in self.ELSTER_ID_RX.finditer(text):
            s, e = m.start(), m.end()
            add.append(RecognizerResult("ELSTER_ID", s, e, 1.05))

        # SERVICEKONTO: German government service account
        for m in self.SERVICEKONTO_RX.finditer(text):
            s, e = m.start(), m.end()
            add.append(RecognizerResult("SERVICEKONTO", s, e, 1.01))

        # Authentication secrets — high priority to prevent false negatives
        # PASSWORD: User account password with label
        for m in self.PASSWORD_RX.finditer(text):
            s, e = m.start(), m.end()
            add.append(RecognizerResult("PASSWORD", s, e, 1.06))

        # PIN: Personal identification number with label
        for m in self.PIN_RX.finditer(text):
            s, e = m.start(), m.end()
            add.append(RecognizerResult("PIN", s, e, 1.06))

        # TAN: Transaction authentication number with label
        for m in self.TAN_RX.finditer(text):
            s, e = m.start(), m.end()
            add.append(RecognizerResult("TAN", s, e, 1.04))

        # PUK: PIN unlock key with label
        for m in self.PUK_RX.finditer(text):
            s, e = m.start(), m.end()
            add.append(RecognizerResult("PUK", s, e, 1.06))

        # RECOVERY_CODE: Account recovery code with label
        for m in self.RECOVERY_CODE_RX.finditer(text):
            s, e = m.start(), m.end()
            add.append(RecognizerResult("RECOVERY_CODE", s, e, 1.03))

        # Reference/Tracking Identifiers — business/legal/government context (inject early with high scores)
        # FILE_NUMBER: Labeled file identifiers
        for m in self.FILE_NUMBER_RX.finditer(text):
            s, e = m.start(), m.end()
            add.append(RecognizerResult("FILE_NUMBER", s, e, 1.08))

        # TRANSACTION_NUMBER: Labeled transaction identifiers
        for m in self.TRANSACTION_NUMBER_RX.finditer(text):
            s, e = m.start(), m.end()
            add.append(RecognizerResult("TRANSACTION_NUMBER", s, e, 1.08))

        # CUSTOMER_NUMBER: Labeled customer identifiers
        for m in self.CUSTOMER_NUMBER_RX.finditer(text):
            s, e = m.start(), m.end()
            add.append(RecognizerResult("CUSTOMER_NUMBER", s, e, 1.07))

        # TICKET_ID: Labeled ticket/case identifiers
        for m in self.TICKET_ID_RX.finditer(text):
            s, e = m.start(), m.end()
            add.append(RecognizerResult("TICKET_ID", s, e, 1.07))

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
            # Labeled IDs should beat phone matches; raise score above PHONE_NUMBER
            add.append(RecognizerResult("ID_NUMBER", s, e, 1.02))
        for m in self.LABELED_TAX_VALUE_RX.finditer(text):
            s, e = (m.start(1), m.end(1)) if m.lastindex else (m.start(), m.end())
            add.append(RecognizerResult("TAX_ID", s, e, 1.0))

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

        # Government/Legal IDs - labeled (BEFORE Passports to win overlaps)
        for m in self.DRIVER_LICENSE_LABEL_RX.finditer(text):
            s, e = (m.start(1), m.end(1)) if m.lastindex else (m.start(), m.end())
            # Labeled identity documents should outrank generic passport pattern matches
            add.append(RecognizerResult("DRIVER_LICENSE", s, e, 1.05))
        for m in self.VOTER_ID_LABEL_RX.finditer(text):
            s, e = (m.start(1), m.end(1)) if m.lastindex else (m.start(), m.end())
            add.append(RecognizerResult("VOTER_ID", s, e, 1.05))
        for m in self.RESIDENCE_PERMIT_LABEL_RX.finditer(text):
            s, e = (m.start(1), m.end(1)) if m.lastindex else (m.start(), m.end())
            add.append(RecognizerResult("RESIDENCE_PERMIT", s, e, 1.05))
        for m in self.BENEFIT_ID_LABEL_RX.finditer(text):
            s, e = (m.start(1), m.end(1)) if m.lastindex else (m.start(), m.end())
            add.append(RecognizerResult("BENEFIT_ID", s, e, 1.05))
        for m in self.MILITARY_ID_LABEL_RX.finditer(text):
            s, e = (m.start(1), m.end(1)) if m.lastindex else (m.start(), m.end())
            add.append(RecognizerResult("MILITARY_ID", s, e, 1.05))

        # Passports
        for m in re.finditer(self.US_PASSPORT_REGEX, text):
            s, e = m.start(), m.end()
            left = text[max(0, s - 24):s].lower()
            # Only boost passport score when explicit passport-like keywords are present
            score = 1.05 if any(k in left for k in set(self.PASSPORT_KEYWORDS)) else 0.95
            add.append(RecognizerResult("PASSPORT", s, e, score))
        for m in re.finditer(self.EU_PASSPORT_REGEX, text):
            s, e = m.start(), m.end()
            left = text[max(0, s - 24):s].lower()
            score = 1.05 if any(k in left for k in set(self.PASSPORT_KEYWORDS)) else 0.90
            add.append(RecognizerResult("PASSPORT", s, e, score))

        # IP
        for patt in (self.IPV4_REGEX, self.IPV6_REGEX):
            for m in re.finditer(patt, text, flags=re.I | re.UNICODE):
                add.append(RecognizerResult("IP_ADDRESS", m.start(), m.end(), 0.95))

        # Credit Cards - labeled gets highest score. Prefer card when brand or label present.
        # Skip candidate if it overlaps a validated IBAN/BIC span to avoid splitting IBANs.
        def _overlaps(spans, s, e):
            return any(not (e <= ss or s >= ee) for (ss, ee) in spans)
        for m in re.finditer(r"(?:(?<!\w)(?:\d[ -]?){13,19}\d(?!\w))", text, flags=re.I | re.UNICODE):
            raw = m.group()
            digits = re.sub(r"[^\d]", "", raw)
            if self._luhn_ok(digits):
                s, e = m.start(), m.end()
                # avoid hijacking validated IBAN or BIC spans
                if _overlaps(validated_iban_spans, s, e) or _overlaps(validated_bic_spans, s, e):
                    continue
                left = text[max(0, s - 24):s].lower()
                if re.search(r"\b(visa|mastercard|master card|amex|american express|diners|jcb)\b", left):
                    # Brand/left-context detected — ensure credit card beats IMEI and other device-like matches
                    score = 1.14
                else:
                    score = 1.02
                add.append(RecognizerResult("CREDIT_CARD", s, e, score))
        for m in self.LABELED_CC_RX.finditer(text):
            s, e = (m.start(1), m.end(1)) if m.lastindex else (m.start(), m.end())
            raw = text[s:e]
            digits = re.sub(r"[^\d]", "", raw)
            if self._luhn_ok(digits):
                add.append(RecognizerResult("CREDIT_CARD", s, e, 1.08))

        # IMEI (validated) — handled in the Devices section below with label-aware scoring
        # (kept out of the earlier injection list to avoid duplicate entries)

        # IBAN (validated) - high score to win overlaps
        for m in self.IBAN_RX.finditer(text):
            # Skip spans that are clearly part of an email
            if self._span_inside_email(text, m.start(), m.end()):
                continue
            # Avoid false positives where a common short preposition (e.g., 'at', 'in', 'am') looks like a country code
            m_left = re.search(r"(\b\w+)\s*$", text[:m.start()])
            if m_left and m_left.group(1).lower() in ("at", "in", "on", "am", "an", "im", "bei", "auf"):
                continue
            if self._iban_ok(m.group()):
                # Make validated IBANs win numeric overlaps (e.g., prevent CREDIT_CARD inside IBAN)
                add.append(RecognizerResult("BANK_ACCOUNT", m.start(), m.end(), 1.12))

        # BIC (uppercase + ISO check)
        for m in self.BIC_RX.finditer(text):
            if self._span_inside_email(text, m.start(), m.end()):
                continue
            if m.group(2) in self.ISO_COUNTRIES:
                add.append(RecognizerResult("BANK_ACCOUNT", m.start(), m.end(), 0.90))

        # Labeled bank/Account with guards
        for m in self.ACCT_LABEL_RX.finditer(text):
            s, e = (m.start(1), m.end(1)) if m.lastindex else (m.start(), m.end())
            val = text[s:e].strip()
            if '@' in val:
                continue
            if self._span_inside_email(text, s, e):
                continue
            if re.match(r'^[A-Za-z]{5,}$', val) and ' ' not in val:
                if not (self._iban_ok(val) or self.BIC_RX.fullmatch(val) or re.search(r'\d', val)):
                    continue
            # DEBUG: guard against accidental plain-word bank matches
            if re.match(r'^[A-Za-z]{3,}$', val) and not re.search(r'\d', val):
                # If the candidate is a short/all-alpha token without IBAN/BIC/digits, skip – avoid "beispiel"→BANK
                # (This avoids bank labels capturing nearby words like email domains or stray tokens)
                continue
            # If the label explicitly mentions IBAN, treat as BANK_ACCOUNT even if not checksum-valid
            label_prefix = text[m.start():m.start(1)].lower()
            if "iban" in label_prefix:
                add.append(RecognizerResult("BANK_ACCOUNT", s, e, 1.02))
                continue
            if self._iban_ok(val):
                add.append(RecognizerResult("BANK_ACCOUNT", s, e, 0.99))
                continue
            m2 = self.BIC_RX.fullmatch(val)
            if m2 and m2.group(2) in self.ISO_COUNTRIES:
                add.append(RecognizerResult("BANK_ACCOUNT", s, e, 0.92))
                continue
            compact = re.sub(r"[^\w]", "", val)
            if 8 <= len(compact) <= 34 and re.match(r"^[A-Za-z0-9]+$", compact):
                # Labeled account numbers should beat common phone/other matches
                # Boost score above typical PHONE/OTHER matches so labeled account wins overlap resolution
                add.append(RecognizerResult("ACCOUNT_NUMBER", s, e, 1.02))

        # Routing numbers (ABA) - boost labeled priority
        for m in self.ROUTING_RX.finditer(text):
            nine = m.group(1) if m.lastindex else m.group(0)
            s1, e1 = (m.start(1), m.end(1)) if m.lastindex else (m.start(0), m.end(0))
            if self._aba_ok(nine):
                left = text[max(0, s1 - 24):s1].lower()
                is_labeled = "routing" in left or "aba" in left or "bankleitzahl" in left
                score = 1.0 if is_labeled else 0.95
                add.append(RecognizerResult("ROUTING_NUMBER", s1, e1, score))

        # Payment/API tokens
        for m in self.PAYMENT_TOKEN_RX.finditer(text):
            # Determine which capturing group matched (group 1 or group 2)
            s = e = None
            if m.lastindex:
                for gi in range(1, m.lastindex + 1):
                    if m.group(gi):
                        s, e = m.start(gi), m.end(gi)
                        break
            if s is None:
                s, e = m.start(), m.end()
            token = text[s:e]
            if len(token) >= 16:
                # If left context explicitly mentions 'api key' (or localizations), prefer PAYMENT_TOKEN
                left_ctx = text[max(0, s - 128):s].lower()
                # Simplified multilingual heuristic: look for 'api' + key/schl variants nearby
                if ("api" in left_ctx) and any(syn in left_ctx for syn in ("key", "schl", "schlu", "schluessel", "schlüssel", "schlussen")):
                    # Remove any overlapping API_KEY injections so PAYMENT_TOKEN wins
                    add = [r for r in add if not (r.entity_type == "API_KEY" and not (e <= r.start or s >= r.end))]
                    add.append(RecognizerResult("PAYMENT_TOKEN", s, e, 1.07))
                else:
                    add.append(RecognizerResult("PAYMENT_TOKEN", s, e, 0.92))

        # Crypto
        for rx in (self.CRYPTO_BTC_LEGACY, self.CRYPTO_BTC_BECH32, self.CRYPTO_ETH):
            for m in rx.finditer(text):
                s, e = m.start(), m.end()
                left_ctx = text[max(0, s - 40):s].lower()
                # If labeled with BTC/ETH or nearby 'Adresse' cue, boost score so CRYPTO wins
                if any(k in left_ctx for k in ("btc", "bitcoin", "bech32", "eth", "ethereum", "adresse")):
                    score = 1.20
                else:
                    score = 0.90
                add.append(RecognizerResult("CRYPTO_ADDRESS", s, e, score))

        # Post-process: stripe/openai-like API_KEY tokens remain as API_KEY
        # for consistency and to meet test requirements. These are actual API keys that should
        # be classified as such, not payment tokens. PAYMENT_TOKEN is reserved for payment-specific tokens.


        # Health IDs & Info
        for m in self.HEALTH_ID_RX.finditer(text):
            s, e = (m.start(1), m.end(1)) if m.lastindex else (m.start(), m.end())
            val = text[s:e]
            if re.search(r"\b\d{3}\s*\d{3}\s*\d{4}\b", val) and self._nhs_ok(val):
                add.append(RecognizerResult("HEALTH_ID", s, e, 1.05))  # Higher than PHONE
            else:
                add.append(RecognizerResult("HEALTH_ID", s, e, 0.95))
        for m in self.MRN_RX.finditer(text):
            s, e = (m.start(1), m.end(1)) if m.lastindex else (m.start(), m.end())
            add.append(RecognizerResult("MRN", s, e, 0.95))  # Increased from 0.90
        for m in self.INSURANCE_ID_RX.finditer(text):
            s, e = (m.start(1), m.end(1)) if m.lastindex else (m.start(), m.end())
            add.append(RecognizerResult("INSURANCE_ID", s, e, 0.95))
        for m in self.HEALTH_INFO_RX.finditer(text):
            add.append(RecognizerResult("HEALTH_INFO", m.start(), m.end(), 1.0))

        # Education/Employment
        for m in self.STUDENT_NUMBER_RX.finditer(text):
            s, e = (m.start(1), m.end(1)) if m.lastindex else (m.start(), m.end())
            add.append(RecognizerResult("STUDENT_NUMBER", s, e, 0.95))  # Increased from 0.88
        for m in self.EMPLOYEE_ID_RX.finditer(text):
            s, e = (m.start(1), m.end(1)) if m.lastindex else (m.start(), m.end())
            add.append(RecognizerResult("EMPLOYEE_ID", s, e, 0.95))  # Increased from 0.90
        for m in self.PRO_LICENSE_RX.finditer(text):
            s, e = (m.start(1), m.end(1)) if m.lastindex else (m.start(), m.end())
            add.append(RecognizerResult("PRO_LICENSE", s, e, 0.95))  # Increased from 0.88

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

        # Devices - boost label-led priorities
        for m in self.MAC_RX.finditer(text):
            add.append(RecognizerResult("MAC_ADDRESS", m.start(), m.end(), 0.90))
        for m in self.IMEI_RX.finditer(text):
            left = text[max(0, m.start() - 24):m.start()].lower()
            is_labeled = bool(re.search(r"\bimei\b", left))
            if self._imei_luhn_ok(m.group()):
                # Ensure valid IMEIs outrank generic credit-card matches; label presence gives slight boost
                score = 1.12 if is_labeled else 1.10
                add.append(RecognizerResult("IMEI", m.start(), m.end(), score))
        for m in self.AD_ID_LABEL_RX.finditer(text):
            add.append(RecognizerResult("ADVERTISING_ID", m.start(1), m.end(1), 1.0))
        for m in self.DEVICE_ID_LABEL_RX.finditer(text):
            s, e = (m.start(1), m.end(1)) if m.lastindex else (m.start(), m.end())
            add.append(RecognizerResult("DEVICE_ID", s, e, 0.88))
        for m in self.DEVICE_ID_PREFIX_RX.finditer(text):
            s, e = (m.start(1), m.end(1)) if m.lastindex else (m.start(), m.end())
            add.append(RecognizerResult("DEVICE_ID", s, e, 1.05))  # Higher score to beat generic ID

        # Geographic coordinates, plus codes and what3words
        for m in self.GEO_COORDS_RX.finditer(text):
            try:
                lat = float(m.group(1))
                lon = float(m.group(2))
                if self._geo_in_bounds(lat, lon):
                    add.append(RecognizerResult("GEO_COORDINATES", m.start(), m.end(), 0.90))
            except Exception:
                pass

        for m in self.PLUS_CODE_RX.finditer(text):
            add.append(RecognizerResult("PLUS_CODE", m.start(), m.end(), 0.90))

        for m in self.W3W_RX.finditer(text):
            add.append(RecognizerResult("W3W", m.start(), m.end(), 0.85))

        # License plate labels
        for m in self.PLATE_LABEL_RX.finditer(text):
            s, e = (m.start(1), m.end(1)) if m.lastindex else (m.start(), m.end())
            plate = re.sub(r"\s+", " ", text[s:e]).strip()
            comp = re.sub(r"[\s\-]", "", plate)
            if 4 <= len(comp) <= 12:
                add.append(RecognizerResult("LICENSE_PLATE", s, e, 0.85))

        # Remove relative DATE tokens from both base results and injected matches (e.g., 'today')
        RELATIVE_DATE_WORDS = {"today","yesterday","tomorrow","tonight","this morning","this afternoon","this evening"}
        def _is_relative_date(r):
            return r.entity_type in ("DATE",) and text[r.start:r.end].strip().lower() in RELATIVE_DATE_WORDS
        results = [r for r in results if not _is_relative_date(r)]
        add = [r for r in add if not _is_relative_date(r)]

        # Remove BANK/ACCOUNT spans that overlap explicit email matches — prevent splitting emails
        email_spans = [(r.start, r.end) for r in add if r.entity_type in ("EMAIL", "EMAIL_ADDRESS")]
        if email_spans:
            def _overlaps_any(s, e, spans):
                return any(not (e <= ss or s >= ee) for (ss, ee) in spans)
            # Filter base results and newly injected candidates
            results = [r for r in results if not (r.entity_type in ("BANK_ACCOUNT", "ACCOUNT_NUMBER") and _overlaps_any(r.start, r.end, email_spans))]
            add = [r for r in add if not (r.entity_type in ("BANK_ACCOUNT", "ACCOUNT_NUMBER") and _overlaps_any(r.start, r.end, email_spans))]

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
            # Direct adjacent ADDRESS <-> LOCATION (existing behavior)
            if i + 1 < len(items):
                nxt = items[i + 1]
                between = text[cur.end:nxt.start]
                if (cur.entity_type == "ADDRESS" and nxt.entity_type == "LOCATION") or \
                   (cur.entity_type == "LOCATION" and nxt.entity_type == "ADDRESS"):
                    if re.fullmatch(r"(?:[ \t]*(?:,|؛|،|;)?[ \t]*|[ \t]*[-–—]?[ \t]*)", between):
                        s = min(cur.start, nxt.start)
                        e = max(cur.end, nxt.end)
                        merged.append(RecognizerResult("ADDRESS", s, e, max(cur.score, nxt.score)))
                        i += 2
                        continue
            # Extended: allow a single numeric filler (DATE/PHONE) between ADDRESS and LOCATION
            if cur.entity_type == "ADDRESS":
                j = i + 1
                interim_ok = True
                while j < len(items) and items[j].entity_type in ("DATE", "PHONE_NUMBER"):
                    span_text = text[items[j].start:items[j].end].strip()
                    # accept numeric-only fillers that look like postcodes or house numbers
                    if not re.fullmatch(r"\d{1,6}", span_text):
                        interim_ok = False
                        break
                    j += 1
                if interim_ok and j < len(items) and items[j].entity_type == "LOCATION":
                    # Merge across numeric fillers (postal code / house number-like tokens)
                    s = min(cur.start, items[j].start)
                    e = max(cur.end, items[j].end)
                    merged.append(RecognizerResult("ADDRESS", s, e, max(cur.score, items[j].score)))
                    i = j + 1
                    continue
            merged.append(cur)
            i += 1
        return self._resolve_overlaps(text, merged)
    

    def add_non_name_tokens_after_ich_bin(self, tokens):
        """
        Extend the 'not-a-name' list for the 'ich bin <token>' rule at runtime.
        """
        if not tokens:
            return
        for w in tokens:
            if isinstance(w, str) and w.strip():
                self.DE_NON_NAME_AFTER_ICH_BIN.add(w.strip().lower())

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
        

            # 🔠 Normalize to NFC so intros like "M\u0306a\u0306" match "Mă"
        try:
             text = unicodedata.normalize("NFC", text)
        except Exception:
            pass


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
            # Drop BANK/ACCOUNT results that are clearly contained in emails or contain no digits
            if r.entity_type in ("BANK_ACCOUNT", "ACCOUNT_NUMBER"):
                span_text = text[r.start:r.end]
                if self._span_inside_email(text, r.start, r.end):
                    continue
                if not re.search(r"\d", span_text):
                    continue
                # Additional guard: require IBAN validation or an explicit nearby bank/account label
                if not (self._iban_ok(span_text) or self.BIC_RX.fullmatch(span_text)):
                    left_ctx = text[max(0, r.start - 28):r.start].lower()
                    if not re.search(r"\b(iban|bic|swift|account|acct|konto|kontonummer|bank|kontonr)\b", left_ctx):
                        # Reject likely false-positive bank spans like short words or adjectives
                        continue
            if r.entity_type == "PERSON":
                span = text[r.start:r.end]
                trimmed, offset = self._trim_intro(span)
                if offset > 0:
                    ns = r.start + offset
                    if (r.end - ns) >= 2:
                        r = RecognizerResult("PERSON", ns, r.end, r.score)
                        span = trimmed
                # If the PERSON span contains a strict-address with a house number, pull it out as ADDRESS
                addr_m = self.STRICT_ADDRESS_RX.search(span)
                if addr_m and re.search(r"\d", addr_m.group()):
                    # Guard against matching education/employment IDs as addresses (e.g., "student ID is STU-12345"
                    # where "student" contains "tal" which is a street suffix in German).
                    broader_ctx = text[max(0, r.start - 50):r.end + 10].lower()
                    if any(label in broader_ctx for label in ["student id", "student number", "studentenausweis",
                                                              "employee id", "employee number",
                                                              "professional license", "license number",
                                                              "pro license", "credential"]):
                        # This is likely an education/employment ID, not an address - skip extracting as ADDRESS
                        if not self._plausible_person(span, text, r.start):
                            continue
                        filtered.append(r)
                        continue
                    # address coordinates in original text
                    addr_s = r.start + (addr_m.start() + (offset if offset else 0))
                    addr_e = r.start + (addr_m.end() + (offset if offset else 0))
                    # keep only the leading person part if it's a plausible person
                    leading = span[:addr_m.start()].strip()
                    if leading and self._plausible_person(leading, text, r.start):
                        new_end = r.start + (addr_m.start() + (offset if offset else 0))
                        if new_end - r.start >= 2:
                            r = RecognizerResult("PERSON", r.start, new_end, r.score)
                            filtered.append(r)
                    # inject address
                    filtered.append(RecognizerResult("ADDRESS", addr_s, addr_e, 1.02))
                    continue
                if not self._plausible_person(span, text, r.start):
                    continue
            filtered.append(r)

        # Intro persons
        filtered = self._inject_name_intro_persons(text, filtered)

        # Custom injections
        final = self._inject_custom_matches(text, filtered)

        # Remove BANK/ACCOUNT spans that overlap with EMAIL spans (avoid replacing parts of emails)
        email_spans = [(r.start, r.end) for r in final if r.entity_type in ("EMAIL", "EMAIL_ADDRESS")]
        if email_spans:
            preserved = []
            for r in final:
                if r.entity_type in ("BANK_ACCOUNT", "ACCOUNT_NUMBER"):
                    # if overlaps any email span, drop
                    if any(not (r.end <= s or r.start >= e) for (s, e) in email_spans):
                        continue
                preserved.append(r)
            final = preserved
        
        # Drop PERSON spans that are clearly non-person single tokens (e.g., Gewerbe)
        # OR multi-token spans that start with sentence structure (pronouns + verbs)
        pruned = []
        for r in final:
            if r.entity_type == 'PERSON':
                span = text[r.start:r.end].strip()
                # Single token check
                if re.fullmatch(r"[A-Za-zÄÖÜäöüßÀ-ÿ]+", span) and span.lower() in self.NON_PERSON_SINGLE_TOKENS:
                    continue
                # Multi-token check: look for sentence-like structure (pronoun + verb + article + noun)
                tokens = [t.lower() for t in span.split()]
                if len(tokens) >= 2:
                    # Check if starts with pronoun or modal verb
                    sentence_starters = {
                        "ich", "du", "er", "sie", "es", "wir", "ihr",  # Pronouns
                        "möchte", "kann", "werde", "würde", "habe", "hab", "bin", "ist", "sind", "hat", "hätte",
                        "für", "von", "zu", "bei", "mit", "ohne", "in",  # Prepositions/articles indicating sentence fragment
                    }
                    # Check first two tokens
                    if any(t in sentence_starters for t in tokens[:2]):
                        continue
            pruned.append(r)
        final = pruned

        # Drop EMAIL / PHONE_NUMBER that appear as a separate labeled line immediately
        # following an ADDRESS line to avoid 'bleed' where labels become attached.
        preserved = []
        addr_spans = [(r.start, r.end) for r in final if r.entity_type == "ADDRESS"]
        for r in final:
            if r.entity_type in ("EMAIL", "EMAIL_ADDRESS", "PHONE_NUMBER"):
                # find the start of the current line
                line_start = text.rfind("\n", 0, r.start)
                if line_start != -1:
                    # check the token left of the line for an ADDRESS that ends before this line
                    if any(aend <= line_start for (astart, aend) in addr_spans):
                        # If the line begins with an obvious label like 'email' or 'telefon', drop the contact entity
                        label = text[line_start + 1:r.start].lower()
                        if re.search(r"\b(email|e-mail|mail|telefon|telefon:|phone|telefonnummer|tel)\b", label):
                            continue
            preserved.append(r)
        final = preserved

        # Filter out PERSON followed by a DATE via connecting prepositions (e.g., 'unter 01.01')
        def _filter_person_before_date_with_prep(text, items):
            out = []
            for r in items:
                if r.entity_type != 'PERSON':
                    out.append(r)
                    continue
                # If a DATE follows within 24 chars and the intervening text contains a preposition like 'unter', drop PERSON
                dropped = False
                # Check for a DATE entity following with a connecting 'unter'
                for d in items:
                    if d.entity_type in ("DATE",) and 0 <= d.start - r.end <= 24:
                        mid = text[r.end:d.start].lower()
                        if re.search(r"\bunter\b", mid):
                            dropped = True
                            break
                # Also check raw right-context like 'unter 12.04' even if no DATE entity was produced
                if not dropped:
                    right = text[r.end:r.end+24].lower()
                    if re.search(r"\bunter\b\s*\d{1,2}[./-]\d{1,2}\b", right):
                        dropped = True
                if dropped:
                    # PERSON followed by date with preposition - skip it
                    pass
                else:
                    out.append(r)
            return out
        final = _filter_person_before_date_with_prep(text, final)

        # Filter out PERSON results that are part of STUDENT_NUMBER patterns
        def _filter_person_student_id(text, items):
            # Find all STUDENT_NUMBER spans first
            student_spans = []
            for m in self.STUDENT_NUMBER_RX.finditer(text):
                s, e = (m.start(1), m.end(1)) if m.lastindex else (m.start(), m.end())
                student_spans.append((s, e))
            
            out = []
            for r in items:
                if r.entity_type != 'PERSON':
                    out.append(r)
                    continue
                # Check if this PERSON span is fully contained within any STUDENT_NUMBER span
                is_student_id = False
                for s, e in student_spans:
                    if s <= r.start and r.end <= e:
                        is_student_id = True
                        break
                if not is_student_id:
                    out.append(r)
            return out
        final = _filter_person_student_id(text, final)

        # Drop LOCATION when a label keyword is inline or adjacent
        final = self._filter_locations_with_inline_or_near_labels(text, final, window=28)

        # strict LOCATION policy — drop standalone city names unless postal/near-address
        final = self._filter_non_postal_locations(text, final, enable=self.STRICT_LOCATION_POSTAL_ONLY)

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
        final = self._demote_phone_over_health_id(text, final)
        final = self._promote_meeting_over_phone(text, final, window=24)

        # Address span trimming
        final = self._trim_address_spans(text, final)

        # ID false-positive filter
        final = self._filter_idnumber_false_positives(text, final)

        # Promote phone-like spans to ACCOUNT_NUMBER when a bank label is immediately left
        final = self._promote_phone_to_account_if_labeled(text, final)

        # Merge address/location
        final = self._merge_address_location(text, final)

        ##print("DEBUG ENTITIES:")
        #for rr in final:
         #   print(rr.entity_type, repr(text[rr.start:rr.end]), rr.start, rr.end)
        #print("----- END DEBUG -----")

        # Replacements: single-escaped HTML tokens
        operators = {
            "PERSON":           OperatorConfig("replace", {"new_value": "<PERSON>"}),
            "EMAIL_ADDRESS":    OperatorConfig("replace", {"new_value": "<EMAIL_ADDRESS>"}),
            "PHONE_NUMBER":     OperatorConfig("replace", {"new_value": "<PHONE_NUMBER>"}),
            "FAX_NUMBER":       OperatorConfig("replace", {"new_value": "<FAX_NUMBER>"}),
            "ADDRESS":          OperatorConfig("replace", {"new_value": "<ADDRESS>"}),
            "LOCATION":         OperatorConfig("replace", {"new_value": "<LOCATION>"}),
            "DATE":             OperatorConfig("replace", {"new_value": "<DATE>"}),
            "PASSPORT":         OperatorConfig("replace", {"new_value": "<PASSPORT>"}),
            "ID_NUMBER":        OperatorConfig("replace", {"new_value": "<ID_NUMBER>"}),
            "TAX_ID":           OperatorConfig("replace", {"new_value": "<TAX_ID>"}),
            "IP_ADDRESS":       OperatorConfig("replace", {"new_value": "<IP_ADDRESS>"}),
            "EORI":             OperatorConfig("replace", {"new_value": "<EORI>"}),
            "COMMERCIAL_REGISTER": OperatorConfig("replace", {"new_value": "<COMMERCIAL_REGISTER>"}),
            "CASE_REFERENCE":   OperatorConfig("replace", {"new_value": "<CASE_REFERENCE>"}),

            "CREDIT_CARD":      OperatorConfig("replace", {"new_value": "<CREDIT_CARD>"}),
            "BANK_ACCOUNT":     OperatorConfig("replace", {"new_value": "<BANK_ACCOUNT>"}),
            "ROUTING_NUMBER":   OperatorConfig("replace", {"new_value": "<ROUTING_NUMBER>"}),
            "ACCOUNT_NUMBER":   OperatorConfig("replace", {"new_value": "<ACCOUNT_NUMBER>"}),
            "PAYMENT_TOKEN":    OperatorConfig("replace", {"new_value": "<PAYMENT_TOKEN>"}),
            "CRYPTO_ADDRESS":   OperatorConfig("replace", {"new_value": "<CRYPTO_ADDRESS>"}),

            "DRIVER_LICENSE":   OperatorConfig("replace", {"new_value": "<DRIVER_LICENSE>"}),
            "VOTER_ID":         OperatorConfig("replace", {"new_value": "<VOTER_ID>"}),
            "RESIDENCE_PERMIT": OperatorConfig("replace", {"new_value": "<RESIDENCE_PERMIT>"}),
            "BENEFIT_ID":       OperatorConfig("replace", {"new_value": "<BENEFIT_ID>"}),
            "MILITARY_ID":      OperatorConfig("replace", {"new_value": "<MILITARY_ID>"}),

            "HEALTH_ID":        OperatorConfig("replace", {"new_value": "<HEALTH_ID>"}),
            "MRN":              OperatorConfig("replace", {"new_value": "<MRN>"}),
            "INSURANCE_ID":     OperatorConfig("replace", {"new_value": "<INSURANCE_ID>"}),
            "HEALTH_INFO":      OperatorConfig("replace", {"new_value": "<HEALTH_INFO>"}),

            "STUDENT_NUMBER":   OperatorConfig("replace", {"new_value": "<STUDENT_NUMBER>"}),
            "EMPLOYEE_ID":      OperatorConfig("replace", {"new_value": "<EMPLOYEE_ID>"}),
            "PRO_LICENSE":      OperatorConfig("replace", {"new_value": "<PRO_LICENSE>"}),

            "SOCIAL_HANDLE":    OperatorConfig("replace", {"new_value": "<SOCIAL_HANDLE>"}),
            "MESSAGING_ID":     OperatorConfig("replace", {"new_value": "<MESSAGING_ID>"}),
            "MEETING_ID":       OperatorConfig("replace", {"new_value": "<MEETING_ID>"}),

            "MAC_ADDRESS":      OperatorConfig("replace", {"new_value": "<MAC_ADDRESS>"}),
            "IMEI":             OperatorConfig("replace", {"new_value": "<IMEI>"}),
            "ADVERTISING_ID":   OperatorConfig("replace", {"new_value": "<ADVERTISING_ID>"}),
            "DEVICE_ID":        OperatorConfig("replace", {"new_value": "<DEVICE_ID>"}),

            "GEO_COORDINATES":  OperatorConfig("replace", {"new_value": "<GEO_COORDINATES>"}),
            "PLUS_CODE":        OperatorConfig("replace", {"new_value": "<PLUS_CODE>"}),
            "W3W":              OperatorConfig("replace", {"new_value": "<W3W>"}),
            "LICENSE_PLATE":    OperatorConfig("replace", {"new_value": "<LICENSE_PLATE>"}),

            "BUND_ID":          OperatorConfig("replace", {"new_value": "<BUND_ID>"}),
            "ELSTER_ID":        OperatorConfig("replace", {"new_value": "<ELSTER_ID>"}),
            "SERVICEKONTO":     OperatorConfig("replace", {"new_value": "<SERVICEKONTO>"}),

            "PASSWORD":         OperatorConfig("replace", {"new_value": "<PASSWORD>"}),
            "PIN":              OperatorConfig("replace", {"new_value": "<PIN>"}),
            "TAN":              OperatorConfig("replace", {"new_value": "<TAN>"}),
            "PUK":              OperatorConfig("replace", {"new_value": "<PUK>"}),
            "RECOVERY_CODE":    OperatorConfig("replace", {"new_value": "<RECOVERY_CODE>"}),

            "FILE_NUMBER":      OperatorConfig("replace", {"new_value": "<FILE_NUMBER>"}),
            "TRANSACTION_NUMBER": OperatorConfig("replace", {"new_value": "<TRANSACTION_NUMBER>"}),
            "CUSTOMER_NUMBER":  OperatorConfig("replace", {"new_value": "<CUSTOMER_NUMBER>"}),
            "TICKET_ID":        OperatorConfig("replace", {"new_value": "<TICKET_ID>"}),

            "API_KEY":          OperatorConfig("replace", {"new_value": "<API_KEY>"}),
            "SESSION_ID":       OperatorConfig("replace", {"new_value": "<SESSION_ID>"}),
            "ACCESS_TOKEN":     OperatorConfig("replace", {"new_value": "<ACCESS_TOKEN>"}),
            "REFRESH_TOKEN":    OperatorConfig("replace", {"new_value": "<REFRESH_TOKEN>"}),
            "ACCESS_CODE":      OperatorConfig("replace", {"new_value": "<ACCESS_CODE>"}),
            "OTP_CODE":         OperatorConfig("replace", {"new_value": "<OTP_CODE>"}),
        }       

        out = self.anonymizer.anonymize(text=text, analyzer_results=final, operators=operators)
        return out.text
