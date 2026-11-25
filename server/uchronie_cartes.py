"""Cartes de départ exactes d'Uchronie pour les grandes dates (écrites à la main, pas par l'IA).

Pour ces années, le monde apparaît tout de suite, sans erreur et sans consommer d'IA. Pour une année proche ou un
« Et si… ? », l'IA part de la carte exacte la plus proche et ne fait que l'ajuster.

Chaque nation donne la liste des territoires qu'elle gouverne à la date indiquée (colonies, protectorats, mandats,
condominiums et territoires sous tutelle compris). Un territoire absent de toutes les listes est un pays indépendant
à son nom. La carte suit les frontières d'aujourd'hui : quand un territoire actuel était partagé (Pologne en 1914,
Allemagne en 1962…), il va à celui qui en tenait la plus grande partie, et la description le précise.
"""
from __future__ import annotations


def N(nid, name, color="", leader="", regime="", desc="", territories=None):
    return {"id": nid, "name": name, "color": color, "leader": leader, "regime": regime, "desc": desc,
            "territories": territories or [nid]}


# Couleurs habituelles des grandes puissances (reprises d'une époque à l'autre)
GB, FR, DE, RU, IT, JP, US, ES, PT, NL, BE, TR, CN, AT = ("#c0392b", "#2e5fc4", "#6b7280", "#8e1b1b", "#2e9e5b",
    "#e0b13c", "#5b8def", "#e08a1e", "#1f7a4d", "#f26b1d", "#d9b70d", "#7a4b2a", "#d94f70", "#e5d3a1")

PRESETS: dict[int, dict] = {}

# ------------------------------------------------------------------ 1914
PRESETS[1914] = {
    "date": "1er janvier 1914",
    "summary": (
        "L'Europe domine le monde : les empires britannique et français se partagent l'Afrique et une grande partie de "
        "l'Asie. Deux blocs se font face : la Triple-Entente (France, Royaume-Uni, Russie) et la Triple-Alliance "
        "(Allemagne, Autriche-Hongrie, Italie). L'Allemagne de Guillaume II rivalise avec la flotte britannique. "
        "Les Balkans sortent de deux guerres (1912-1913) : la Serbie s'est agrandie et inquiète l'Autriche-Hongrie. "
        "L'Empire ottoman, affaibli, a perdu presque toute l'Europe et la Libye. La Chine est une jeune république "
        "instable, le Japon une puissance montante qui tient la Corée et Taïwan. Les États-Unis restent à l'écart "
        "des affaires européennes. La course aux armements bat son plein."),
    "nations": [
        N("gbr", "Empire britannique", GB, "George V (Premier ministre : H. H. Asquith)", "monarchie parlementaire",
          "Le plus vaste empire du monde, première flotte mondiale. Ses dominions (Canada, Australie…) le suivent.",
          ["gbr", "irl", "imn", "can", "aus", "nzl", "zaf", "ind", "pak", "bgd", "mmr", "lka", "mys", "sgp", "brn",
           "hkg", "egy", "sdn", "ssd", "ken", "uga", "zwe", "zmb", "mwi", "bwa", "lso", "swz", "nga", "gha", "sle",
           "gmb", "somaliland", "cyp", "ncyprus", "mlt", "are", "bhr", "jam", "bhs", "brb", "tto", "lca", "dma", "blz",
           "guy", "flk", "fji", "slb", "kir", "vut", "mus"]),
        N("fra", "République française", FR, "Raymond Poincaré", "IIIe République",
          "Deuxième empire colonial. Veut reprendre l'Alsace-Lorraine, perdue en 1871. Alliée de la Russie.",
          ["fra", "dza", "tun", "mar", "mrt", "sen", "mli", "gin", "civ", "bfa", "ben", "ner", "tcd", "caf", "cog",
           "gab", "mdg", "com", "dji", "vnm", "lao", "khm", "ncl", "pyf"]),
        N("deu", "Empire allemand", DE, "Guillaume II (chancelier : Bethmann Hollweg)", "monarchie impériale",
          "Première armée et première industrie d'Europe. Tient aussi l'Alsace-Lorraine et l'ouest de la Pologne.",
          ["deu", "cmr", "tgo", "nam", "tza", "rwa", "bdi", "png", "wsm"]),
        N("aut", "Autriche-Hongrie", AT, "François-Joseph Ier", "double monarchie",
          "Empire de nombreux peuples, inquiet du nationalisme serbe. Allié de l'Allemagne.",
          ["aut", "hun", "cze", "svk", "svn", "hrv", "bih"]),
        N("rus", "Empire russe", RU, "Nicolas II", "autocratie",
          "Immense empire agricole en pleine industrialisation, protecteur des Slaves des Balkans. Tient la Finlande "
          "et la plus grande partie de la Pologne.",
          ["rus", "ukr", "blr", "pol", "ltu", "lva", "est", "fin", "ala", "mda", "geo", "arm", "aze", "kaz", "uzb",
           "tkm", "kgz", "tjk"]),
        N("tur", "Empire ottoman", TR, "Mehmed V (gouvernement des Jeunes-Turcs)", "monarchie sous un parti unique",
          "Empire affaibli qui garde l'Anatolie, le Levant, la Mésopotamie et l'ouest de l'Arabie.",
          ["tur", "syr", "lbn", "isr", "pse", "jor", "irq", "yem"]),
        N("ita", "Royaume d'Italie", IT, "Victor-Emmanuel III (président du Conseil : Giolitti)", "monarchie constitutionnelle",
          "Membre de la Triple-Alliance mais hésitant. Vient de prendre la Libye aux Ottomans (1912).",
          ["ita", "lby", "eri", "som"]),
        N("esp", "Royaume d'Espagne", ES, "Alphonse XIII", "monarchie constitutionnelle",
          "Puissance déclinante, neutre, présente au Maroc et en Guinée.", ["esp", "esh", "gnq"]),
        N("prt", "République portugaise", PT, "Manuel de Arriaga", "Ire République",
          "Jeune république instable, mais grand empire africain.", ["prt", "ago", "moz", "gnb", "cpv", "stp", "tls"]),
        N("bel", "Royaume de Belgique", BE, "Albert Ier", "monarchie constitutionnelle",
          "Pays neutre garanti par les grandes puissances, maître du Congo.", ["bel", "cod"]),
        N("nld", "Royaume des Pays-Bas", NL, "Wilhelmine", "monarchie constitutionnelle",
          "Neutre, riche de ses Indes orientales.", ["nld", "idn", "sur", "cuw"]),
        N("dnk", "Royaume de Danemark", "#b83b5e", "Christian X", "monarchie constitutionnelle", "Neutre.",
          ["dnk", "isl", "grl", "fro"]),
        N("usa", "États-Unis", US, "Woodrow Wilson", "république fédérale",
          "Première économie du monde, isolationniste. Le canal de Panama ouvre cette année.",
          ["usa", "phl", "pri", "gum"]),
        N("jpn", "Empire du Japon", JP, "Taishō (Yoshihito)", "monarchie impériale",
          "Puissance montante, allié du Royaume-Uni, maître de la Corée et de Taïwan.", ["jpn", "kor", "prk", "twn"]),
        N("chn", "République de Chine", CN, "Yuan Shikai", "république autoritaire",
          "Née en 1912 de la chute des Qing, divisée et convoitée par les puissances."),
        N("srb", "Royaume de Serbie", "#4b6cb7", "Pierre Ier", "monarchie constitutionnelle",
          "Agrandie par les guerres balkaniques (Kosovo, Macédoine), soutenue par la Russie.", ["srb", "kosovo", "mkd"]),
        N("mne", "Royaume du Monténégro", "#9b59b6", "Nicolas Ier"),
        N("grc", "Royaume de Grèce", "#3a9ad9", "Constantin Ier", "monarchie constitutionnelle"),
        N("bgr", "Royaume de Bulgarie", "#2f8f83", "Ferdinand Ier", "monarchie", "Amère après sa défaite de 1913."),
        N("rou", "Royaume de Roumanie", "#d4a017", "Carol Ier", "monarchie constitutionnelle"),
        N("alb", "Principauté d'Albanie", "#a04040", "Guillaume de Wied (arrive en mars)", "principauté", "État créé en 1913."),
        N("swe", "Royaume de Suède", "#3d7dd8", "Gustave V"), N("nor", "Royaume de Norvège", "#c45a8a", "Haakon VII"),
        N("che", "Suisse", "#e74c3c", "", "confédération", "Neutre."),
        N("irn", "Perse", "#16a085", "Ahmad Shah Qadjar", "monarchie", "Partagée en zones d'influence russe et britannique."),
        N("afg", "Émirat d'Afghanistan", "#7d6608", "Habibullah Khan", "émirat"),
        N("sau", "Émirat du Nejd", "#6e8b3d", "Abdelaziz ibn Saoud", "émirat", "Rival des Ottomans au cœur de l'Arabie."),
        N("tha", "Royaume de Siam", "#8e44ad", "Rama VI", "monarchie absolue"),
        N("eth", "Empire d'Éthiopie", "#27ae60", "Lij Iyasu", "empire", "Un des deux seuls États africains indépendants."),
        N("lbr", "Libéria", "#5dade2"),
        N("mng", "Mongolie", "#48c9b0", "Bogd Khan", "théocratie", "Autonome depuis 1911, entre Chine et Russie."),
        N("kwt", "Cheikhat du Koweït", "#a3e4d7", "Moubarak al-Sabah"),
        N("mex", "Mexique", "#58d68d", "Victoriano Huerta", "dictature", "En pleine révolution."),
        N("bra", "Brésil", "#2ecc71", "Hermes da Fonseca", "république"),
        N("arg", "Argentine", "#85c1e9", "Roque Sáenz Peña", "république"),
    ],
}

# ------------------------------------------------------------------ 1936
PRESETS[1936] = {
    "date": "1er janvier 1936",
    "summary": (
        "La crise économique de 1929 frappe toujours le monde. En Allemagne, Hitler réarme à grande vitesse et rêve "
        "de revanche ; l'Italie de Mussolini fait la guerre en Éthiopie malgré la Société des Nations. La France et "
        "le Royaume-Uni, à la tête des deux plus grands empires coloniaux, hésitent à réagir. L'Union soviétique de "
        "Staline s'industrialise à marche forcée. Le Japon militariste occupe la Mandchourie (État fantoche du "
        "Mandchoukouo) et menace la Chine de Tchang Kaï-chek, elle-même en guerre contre les communistes. "
        "L'Espagne est au bord de la guerre civile. Les États-Unis de Roosevelt sont absorbés par le New Deal."),
    "nations": [
        N("gbr", "Empire britannique", GB, "George V (Premier ministre : Stanley Baldwin)", "monarchie parlementaire",
          "Le plus vaste empire du monde, épuisé par la crise. Ses dominions sont désormais souverains.",
          ["gbr", "imn", "ind", "pak", "bgd", "mmr", "lka", "mys", "sgp", "brn", "hkg", "sdn", "ssd", "ken", "uga",
           "tza", "zwe", "zmb", "mwi", "bwa", "lso", "swz", "nga", "gha", "sle", "gmb", "somaliland", "jor", "isr",
           "pse", "cyp", "ncyprus", "mlt", "are", "bhr", "qat", "kwt", "jam", "bhs", "brb", "tto", "lca", "dma",
           "blz", "guy", "flk", "fji", "slb", "kir", "vut", "mus"]),
        N("fra", "République française", FR, "Albert Lebrun (président du Conseil : Pierre Laval)", "IIIe République",
          "Deuxième empire colonial, première armée d'Europe sur le papier, mais divisée et prudente.",
          ["fra", "dza", "tun", "mar", "mrt", "sen", "mli", "gin", "civ", "bfa", "ben", "ner", "tcd", "caf", "cog",
           "gab", "cmr", "tgo", "mdg", "com", "dji", "syr", "lbn", "vnm", "lao", "khm", "ncl", "pyf"]),
        N("deu", "Reich allemand", DE, "Adolf Hitler", "dictature nazie",
          "Réarme en violation du traité de Versailles. Veut réunir les germanophones et s'étendre à l'Est."),
        N("ita", "Royaume d'Italie", IT, "Benito Mussolini (roi : Victor-Emmanuel III)", "dictature fasciste",
          "En guerre en Éthiopie, rêve d'un empire méditerranéen.", ["ita", "lby", "eri", "som"]),
        N("rus", "Union soviétique", RU, "Joseph Staline", "dictature communiste",
          "Industrialisation forcée et répression. Se méfie à la fois de l'Allemagne et du Japon.",
          ["rus", "ukr", "blr", "geo", "arm", "aze", "kaz", "uzb", "tkm", "kgz", "tjk"]),
        N("jpn", "Empire du Japon", JP, "Hirohito", "empire militariste",
          "Contrôle aussi la Mandchourie (Mandchoukouo, dans le nord-est de la Chine). Veut dominer l'Asie.",
          ["jpn", "kor", "prk", "twn"]),
        N("usa", "États-Unis", US, "Franklin D. Roosevelt", "république fédérale",
          "Première économie du monde, isolationniste, en plein New Deal. Les Philippines préparent leur indépendance.",
          ["usa", "phl", "pri", "gum"]),
        N("chn", "République de Chine", CN, "Tchang Kaï-chek", "parti unique (Kuomintang)",
          "Divisée entre seigneurs de la guerre, communistes de Mao et menace japonaise."),
        N("esp", "République espagnole", ES, "Niceto Alcalá-Zamora", "IIe République",
          "Pays déchiré entre gauche et droite, à quelques mois de la guerre civile.", ["esp", "esh", "gnq"]),
        N("prt", "Portugal", PT, "António de Oliveira Salazar", "dictature (Estado Novo)", "",
          ["prt", "ago", "moz", "gnb", "cpv", "stp", "tls"]),
        N("bel", "Royaume de Belgique", BE, "Léopold III", "monarchie constitutionnelle", "",
          ["bel", "cod", "rwa", "bdi"]),
        N("nld", "Royaume des Pays-Bas", NL, "Wilhelmine", "monarchie constitutionnelle", "",
          ["nld", "idn", "sur", "cuw"]),
        N("dnk", "Royaume de Danemark", "#b83b5e", "Christian X", "monarchie constitutionnelle", "",
          ["dnk", "grl", "fro"]),
        N("can", "Canada", "#e57373", "W. L. Mackenzie King", "dominion britannique"),
        N("aus", "Australie", "#ef6c00", "Joseph Lyons", "dominion britannique",
          "Administre aussi la Nouvelle-Guinée.", ["aus", "png"]),
        N("nzl", "Nouvelle-Zélande", "#8d6e63", "Michael Joseph Savage", "dominion britannique", "", ["nzl", "wsm"]),
        N("zaf", "Union sud-africaine", "#a1887f", "J. B. M. Hertzog", "dominion britannique",
          "Administre aussi le Sud-Ouest africain.", ["zaf", "nam"]),
        N("irl", "État libre d'Irlande", "#66bb6a", "Éamon de Valera", "dominion britannique"),
        N("cze", "Tchécoslovaquie", "#4a90c2", "Edvard Beneš", "démocratie", "Alliée de la France.", ["cze", "svk"]),
        N("srb", "Royaume de Yougoslavie", "#4b6cb7", "Pierre II (régent : prince Paul)", "monarchie",
          "", ["srb", "hrv", "svn", "bih", "mne", "mkd", "kosovo"]),
        N("pol", "Pologne", "#dc4c64", "Ignacy Mościcki", "régime autoritaire", "Coincée entre l'Allemagne et l'URSS."),
        N("rou", "Royaume de Roumanie", "#d4a017", "Carol II", "monarchie", "", ["rou", "mda"]),
        N("hun", "Royaume de Hongrie", "#9c640c", "Miklós Horthy (régent)", "régence autoritaire"),
        N("aut", "Autriche", AT, "Kurt Schuschnigg", "dictature austrofasciste", "Menacée d'annexion par l'Allemagne."),
        N("fin", "Finlande", "#5d9cec", "Pehr Evind Svinhufvud", "république", "", ["fin", "ala"]),
        N("tur", "République de Turquie", TR, "Mustafa Kemal Atatürk", "république à parti unique"),
        N("sau", "Royaume d'Arabie saoudite", "#6e8b3d", "Abdelaziz ibn Saoud", "monarchie absolue"),
        N("irn", "Iran", "#16a085", "Reza Shah Pahlavi", "monarchie autoritaire"),
        N("irq", "Royaume d'Irak", "#b9770e", "Ghazi Ier", "monarchie"),
        N("egy", "Royaume d'Égypte", "#c9a227", "Fouad Ier", "monarchie", "Indépendante mais occupée par des troupes britanniques."),
        N("eth", "Empire d'Éthiopie", "#27ae60", "Hailé Sélassié Ier", "empire", "Envahie par l'Italie depuis octobre 1935."),
        N("tha", "Royaume de Siam", "#8e44ad", "Rama VIII (régence)", "monarchie constitutionnelle"),
        N("mng", "République populaire de Mongolie", "#48c9b0", "Khorloogiin Choibalsan", "régime communiste",
          "Satellite de l'URSS."),
        N("yem", "Royaume du Yémen", "#a3e4d7", "Yahya Muhammad Hamid ed-Din", "imamat",
          "Aden, au sud, est britannique."),
        N("isl", "Royaume d'Islande", "#5dade2", "Christian X", "monarchie (union personnelle avec le Danemark)"),
        N("grc", "Royaume de Grèce", "#3a9ad9", "Georges II", "monarchie"),
        N("bgr", "Royaume de Bulgarie", "#2f8f83", "Boris III", "monarchie autoritaire"),
        N("alb", "Royaume d'Albanie", "#a04040", "Zog Ier", "monarchie", "Sous forte influence italienne."),
        N("mex", "Mexique", "#58d68d", "Lázaro Cárdenas", "république"),
        N("bra", "Brésil", "#2ecc71", "Getúlio Vargas", "régime autoritaire"),
        N("arg", "Argentine", "#85c1e9", "Agustín P. Justo", "république"),
    ],
}

# ------------------------------------------------------------------ 1962
PRESETS[1962] = {
    "date": "1er janvier 1962",
    "summary": (
        "Pleine guerre froide : les États-Unis de Kennedy et l'URSS de Khrouchtchev s'affrontent par alliés interposés, "
        "sous la menace nucléaire. Le mur de Berlin vient d'être construit (août 1961). L'Europe est coupée en deux : "
        "OTAN à l'ouest, pacte de Varsovie à l'est. La décolonisation est presque achevée en Afrique, mais la France "
        "mène encore la guerre d'Algérie et le Portugal s'accroche à ses colonies. Cuba, devenue communiste, est "
        "soutenue par Moscou après l'échec du débarquement de la baie des Cochons. La Chine de Mao a rompu avec l'URSS. "
        "Le Vietnam est coupé en deux et la guérilla communiste progresse au Sud."),
    "nations": [
        N("usa", "États-Unis", US, "John F. Kennedy", "république fédérale",
          "Superpuissance, chef de l'OTAN.", ["usa", "pri", "gum"]),
        N("rus", "Union soviétique", RU, "Nikita Khrouchtchev", "État communiste",
          "Superpuissance, chef du pacte de Varsovie.",
          ["rus", "ukr", "blr", "est", "lva", "ltu", "mda", "geo", "arm", "aze", "kaz", "uzb", "tkm", "kgz", "tjk"]),
        N("gbr", "Royaume-Uni", GB, "Élisabeth II (Premier ministre : Harold Macmillan)", "monarchie parlementaire",
          "Empire en décolonisation, puissance nucléaire.",
          ["gbr", "imn", "hkg", "sgp", "brn", "ken", "uga", "zwe", "zmb", "mwi", "bwa", "lso", "swz", "gmb", "mus",
           "jam", "tto", "brb", "lca", "dma", "bhs", "blz", "guy", "flk", "fji", "slb", "kir", "vut", "are", "bhr",
           "qat", "mlt"]),
        N("fra", "République française", FR, "Charles de Gaulle", "Ve République",
          "En pleine guerre d'Algérie, veut une France indépendante des deux blocs. Puissance nucléaire depuis 1960.",
          ["fra", "dza", "com", "dji", "ncl", "pyf"]),
        N("deu", "Allemagne de l'Ouest (RFA)", "#9aa5b1", "Konrad Adenauer", "république fédérale",
          "Membre de l'OTAN en plein miracle économique. (Sur cette carte, le territoire inclut la RDA communiste.)"),
        N("chn", "République populaire de Chine", CN, "Mao Zedong", "État communiste",
          "En rupture avec l'URSS, sort du désastre du Grand Bond en avant."),
        N("twn", "République de Chine (Taïwan)", "#f48fb1", "Tchang Kaï-chek", "parti unique",
          "Réfugiée à Taïwan, occupe le siège de la Chine à l'ONU."),
        N("jpn", "Japon", JP, "Hayato Ikeda (empereur : Hirohito)", "monarchie parlementaire",
          "Allié des États-Unis, croissance économique très rapide."),
        N("prt", "Portugal", PT, "António de Oliveira Salazar", "dictature (Estado Novo)",
          "Refuse de lâcher ses colonies ; la guerre a commencé en Angola.",
          ["prt", "ago", "moz", "gnb", "cpv", "stp", "tls"]),
        N("esp", "Espagne", ES, "Francisco Franco", "dictature", "", ["esp", "esh", "gnq"]),
        N("bel", "Royaume de Belgique", BE, "Baudouin Ier", "monarchie constitutionnelle",
          "Le Rwanda et le Burundi sont sous sa tutelle jusqu'à leur indépendance en juillet 1962.",
          ["bel", "rwa", "bdi"]),
        N("nld", "Royaume des Pays-Bas", NL, "Juliana", "monarchie constitutionnelle", "", ["nld", "sur", "cuw"]),
        N("dnk", "Royaume de Danemark", "#b83b5e", "Frederik IX", "monarchie constitutionnelle", "",
          ["dnk", "grl", "fro"]),
        N("aus", "Australie", "#ef6c00", "Robert Menzies", "monarchie parlementaire",
          "Administre la Papouasie-Nouvelle-Guinée.", ["aus", "png"]),
        N("zaf", "Afrique du Sud", "#a1887f", "Hendrik Verwoerd", "république d'apartheid",
          "Administre aussi le Sud-Ouest africain (Namibie).", ["zaf", "nam"]),
        N("ita", "Italie", IT, "Amintore Fanfani", "république parlementaire"),
        N("can", "Canada", "#e57373", "John Diefenbaker", "monarchie parlementaire"),
        N("ind", "Inde", "#ff8f00", "Jawaharlal Nehru", "république parlementaire", "Chef de file des non-alignés."),
        N("pak", "Pakistan", "#00897b", "Muhammad Ayub Khan", "régime militaire",
          "Formé de deux parties : l'ouest et le Bengale oriental.", ["pak", "bgd"]),
        N("egy", "République arabe unie (Égypte)", "#c9a227", "Gamal Abdel Nasser", "république nationaliste",
          "Champion du nationalisme arabe ; la Syrie a quitté l'union en 1961."),
        N("isr", "Israël", "#1e88e5", "David Ben Gourion", "démocratie parlementaire"),
        N("jor", "Royaume de Jordanie", "#b9770e", "Hussein Ier", "monarchie", "Tient la Cisjordanie et Jérusalem-Est.",
          ["jor", "pse"]),
        N("cub", "Cuba", "#d81b60", "Fidel Castro", "régime communiste", "Allié de l'URSS à 150 km de la Floride."),
        N("srb", "Yougoslavie", "#4b6cb7", "Josip Broz Tito", "État communiste non aligné", "",
          ["srb", "hrv", "svn", "bih", "mne", "mkd", "kosovo"]),
        N("cze", "Tchécoslovaquie", "#4a90c2", "Antonín Novotný", "État communiste", "", ["cze", "svk"]),
        N("pol", "Pologne", "#dc4c64", "Władysław Gomułka", "État communiste"),
        N("eth", "Empire d'Éthiopie", "#27ae60", "Hailé Sélassié Ier", "empire", "Fédérée avec l'Érythrée.", ["eth", "eri"]),
        N("som", "Somalie", "#4fc3f7", "Aden Abdullah Osman Daar", "république", "", ["som", "somaliland"]),
        N("sdn", "Soudan", "#bf9b30", "Ibrahim Abboud", "régime militaire", "", ["sdn", "ssd"]),
        N("cyp", "Chypre", "#ffb74d", "Makarios III", "république", "", ["cyp", "ncyprus"]),
        N("fin", "Finlande", "#5d9cec", "Urho Kekkonen", "république", "", ["fin", "ala"]),
        N("vnm", "Viêt Nam (divisé)", "#c62828", "Hô Chi Minh (Nord) · Ngô Đình Diệm (Sud)", "Nord communiste, Sud pro-américain",
          "Coupé en deux au 17e parallèle ; la guérilla du Viêt-Cong progresse au Sud."),
        N("kor", "Corée du Sud", "#64b5f6", "Park Chung-hee", "régime militaire"),
        N("prk", "Corée du Nord", "#b71c1c", "Kim Il-sung", "État communiste"),
        N("idn", "Indonésie", "#e53935", "Soekarno", "démocratie dirigée", "Réclame la Nouvelle-Guinée occidentale aux Pays-Bas."),
        N("cod", "Congo-Léopoldville", "#7cb342", "Joseph Kasa-Vubu", "république", "En pleine crise (sécession du Katanga)."),
        N("cog", "Congo-Brazzaville"), N("bfa", "Haute-Volta"), N("ben", "Dahomey"),
        N("tza", "Tanganyika", "", "Julius Nyerere", "république", "Indépendant depuis décembre 1961."),
        N("lka", "Ceylan"), N("mmr", "Birmanie", "", "U Nu"), N("tha", "Thaïlande", "#8e44ad", "Bhumibol (Rama IX)"),
        N("irn", "Iran", "#16a085", "Mohammad Reza Pahlavi", "monarchie"),
        N("sau", "Arabie saoudite", "#6e8b3d", "Saoud ben Abdelaziz", "monarchie absolue"),
        N("yem", "Royaume du Yémen", "#a3e4d7", "Ahmad ben Yahya", "imamat", "Aden, au sud, est britannique."),
        N("mys", "Fédération de Malaisie", "", "Tunku Abdul Rahman"),
        N("lby", "Royaume de Libye", "", "Idris Ier"),
        N("wsm", "Samoa occidentales", "", "", "", "Indépendantes depuis le 1er janvier 1962."),
    ],
}

# ------------------------------------------------------------------ 2025
PRESETS[2025] = {
    "date": "1er janvier 2025",
    "summary": (
        "La guerre en Ukraine entre dans sa troisième année : la Russie occupe environ un cinquième du pays. Au "
        "Proche-Orient, la guerre entre Israël et le Hamas a ravagé Gaza et s'est étendue au Liban ; en Syrie, le "
        "régime de Bachar el-Assad vient de tomber (décembre 2024). Les États-Unis s'apprêtent à voir Donald Trump "
        "revenir à la Maison-Blanche le 20 janvier. La rivalité entre les États-Unis et la Chine domine l'économie "
        "mondiale (technologies, Taïwan). L'Union européenne cherche à se réarmer. L'Inde est devenue le pays le plus "
        "peuplé du monde. Climat, intelligence artificielle et dettes publiques sont au cœur des débats."),
    "nations": [
        N("usa", "États-Unis", US, "Joe Biden (Donald Trump investi le 20 janvier)", "république fédérale",
          "Première puissance mondiale.", ["usa", "pri", "gum"]),
        N("chn", "République populaire de Chine", CN, "Xi Jinping", "État-parti communiste",
          "Deuxième puissance mondiale, revendique Taïwan.", ["chn", "hkg"]),
        N("rus", "Fédération de Russie", RU, "Vladimir Poutine", "régime autoritaire",
          "En guerre contre l'Ukraine, sous sanctions occidentales."),
        N("ukr", "Ukraine", "#ffd54f", "Volodymyr Zelensky", "république",
          "Résiste à l'invasion russe ; environ 20 % de son territoire est occupé."),
        N("fra", "France", FR, "Emmanuel Macron (Premier ministre : François Bayrou)", "Ve République",
          "Puissance nucléaire, en crise politique.", ["fra", "ncl", "pyf"]),
        N("gbr", "Royaume-Uni", GB, "Keir Starmer (roi : Charles III)", "monarchie parlementaire", "",
          ["gbr", "imn", "flk"]),
        N("deu", "Allemagne", DE, "Olaf Scholz", "république fédérale", "Gouvernement tombé, élections en février."),
        N("ita", "Italie", IT, "Giorgia Meloni", "république parlementaire"),
        N("esp", "Espagne", ES, "Pedro Sánchez", "monarchie parlementaire"),
        N("pol", "Pologne", "#dc4c64", "Donald Tusk", "république parlementaire"),
        N("nld", "Pays-Bas", NL, "Dick Schoof", "monarchie parlementaire", "", ["nld", "cuw"]),
        N("dnk", "Danemark", "#b83b5e", "Mette Frederiksen", "monarchie parlementaire", "", ["dnk", "grl", "fro"]),
        N("fin", "Finlande", "#5d9cec", "Alexander Stubb", "république", "", ["fin", "ala"]),
        N("tur", "Turquie", TR, "Recep Tayyip Erdoğan", "république présidentielle"),
        N("ind", "Inde", "#ff8f00", "Narendra Modi", "république parlementaire", "Pays le plus peuplé du monde."),
        N("pak", "Pakistan", "#00897b", "Shehbaz Sharif", "république"),
        N("jpn", "Japon", JP, "Shigeru Ishiba", "monarchie parlementaire"),
        N("kor", "Corée du Sud", "#64b5f6", "Choi Sang-mok (par intérim)", "république", "Le président Yoon a été destitué."),
        N("prk", "Corée du Nord", "#b71c1c", "Kim Jong-un", "dictature"),
        N("twn", "Taïwan", "#f48fb1", "Lai Ching-te", "démocratie"),
        N("isr", "Israël", "#1e88e5", "Benyamin Netanyahou", "démocratie parlementaire", "En guerre à Gaza et au Liban."),
        N("pse", "Palestine", "#43a047", "Mahmoud Abbas", "", "Gaza est dévastée par la guerre."),
        N("irn", "Iran", "#16a085", "Ali Khamenei (président : Massoud Pezeshkian)", "république islamique"),
        N("sau", "Arabie saoudite", "#6e8b3d", "Mohammed ben Salmane", "monarchie absolue"),
        N("syr", "Syrie", "#8d6e63", "Ahmed al-Charaa", "pouvoir de transition", "Assad vient d'être renversé."),
        N("egy", "Égypte", "#c9a227", "Abdel Fattah al-Sissi", "régime autoritaire"),
        N("mar", "Maroc", "#2e7d32", "Mohammed VI", "monarchie", "Contrôle la plus grande partie du Sahara occidental.",
          ["mar", "esh"]),
        N("bra", "Brésil", "#2ecc71", "Luiz Inácio Lula da Silva", "république fédérale"),
        N("mex", "Mexique", "#58d68d", "Claudia Sheinbaum", "république fédérale"),
        N("arg", "Argentine", "#85c1e9", "Javier Milei", "république"),
        N("can", "Canada", "#e57373", "Justin Trudeau", "monarchie parlementaire"),
        N("aus", "Australie", "#ef6c00", "Anthony Albanese", "monarchie parlementaire"),
        N("zaf", "Afrique du Sud", "#a1887f", "Cyril Ramaphosa", "république"),
        N("nga", "Nigéria", "#00a651", "Bola Tinubu", "république fédérale"),
        N("idn", "Indonésie", "#e53935", "Prabowo Subianto", "république"),
        N("vnm", "Viêt Nam", "#c62828", "Tô Lâm", "État-parti communiste"),
        N("afg", "Afghanistan", "#7d6608", "Hibatullah Akhundzada", "émirat taliban"),
        N("ven", "Venezuela", "#fbc02d", "Nicolás Maduro", "régime autoritaire"),
        N("blr", "Biélorussie", "#9e9d24", "Alexandre Loukachenko", "dictature", "Allié de la Russie."),
        N("hun", "Hongrie", "#9c640c", "Viktor Orbán", "république parlementaire"),
        N("ncyprus", "Chypre du Nord", "#ffcc80", "", "", "Reconnue par la seule Turquie."),
    ],
}


def nearest(year: int, span: int = 15) -> int | None:
    """La carte exacte la plus proche de l'année, si elle est à moins de `span` ans."""
    best = min(PRESETS, key=lambda y: abs(y - year))
    return best if abs(best - year) <= span else None
