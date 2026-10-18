/** What to check before and during a viewing; keys are stored, so keep them stable. */
export interface CheckGroup {
  title: string;
  items: { key: string; label: string; primaryOnly?: boolean; secondaryOnly?: boolean }[];
}

export const CHECKLIST: CheckGroup[] = [
  {
    title: "Dokumenty i stan prawny",
    items: [
      { key: "kw", label: "Numer księgi wieczystej – sprawdzony w EKW (właściciel, hipoteka, służebności)" },
      { key: "ownership", label: "Rodzaj własności (pełna / spółdzielcza) i czy jest KW" },
      { key: "debts", label: "Zaświadczenie o braku zaległości (czynsz, media)", secondaryOnly: true },
      { key: "registered", label: "Nikt nie jest zameldowany / zaświadczenie o wymeldowaniu", secondaryOnly: true },
      { key: "rent", label: "Czynsz: ile, co obejmuje, fundusz remontowy, planowane remonty" },
      { key: "plan", label: "Plan miejscowy – co może powstać obok (Geoportal)" },
      { key: "prospectus", label: "Prospekt informacyjny, harmonogram, rachunek powierniczy", primaryOnly: true },
      { key: "standard", label: "Standard wykończenia i co jest w cenie (komórka, miejsce postojowe)", primaryOnly: true },
    ],
  },
  {
    title: "Budynek",
    items: [
      { key: "staircase", label: "Klatka, elewacja, dach – stan i czystość" },
      { key: "elevator", label: "Winda (działa, wielkość)" },
      { key: "storage", label: "Piwnica / komórka lokatorska" },
      { key: "parking", label: "Parking / miejsce postojowe – koszt, dostępność" },
      { key: "noise", label: "Hałas: ulica, tramwaj, sąsiedzi (sprawdź przy zamkniętych oknach)" },
    ],
  },
  {
    title: "Mieszkanie",
    items: [
      { key: "damp", label: "Wilgoć i pleśń: narożniki, za meblami, łazienka, przy oknach" },
      { key: "windows", label: "Okna: szczelność, rok, czy się domykają" },
      { key: "electric", label: "Instalacja elektryczna (miedź czy aluminium, bezpieczniki)" },
      { key: "water", label: "Woda: ciśnienie, czas do ciepłej wody, piony" },
      { key: "heating", label: "Ogrzewanie: grzejniki, podzielniki, koszty zimą" },
      { key: "ventilation", label: "Wentylacja: kratki, czy jest ciąg (kartka)" },
      { key: "sun", label: "Nasłonecznienie i strony świata, widok" },
      { key: "balcony", label: "Balkon: stan, wielkość, ekspozycja" },
      { key: "walls", label: "Ściany i podłogi: pęknięcia, krzywizny" },
      { key: "internet", label: "Zasięg telefonu i internet (światłowód?)" },
    ],
  },
  {
    title: "Okolica",
    items: [
      { key: "commute", label: "Dojazd w praktyce: przystanek, tramwaj w godzinach szczytu" },
      { key: "shops", label: "Sklepy, apteka, paczkomat w zasięgu spaceru" },
      { key: "evening", label: "Okolica wieczorem / w weekend" },
    ],
  },
];

export function checklistFor(market: string | null): CheckGroup[] {
  return CHECKLIST.map((g) => ({
    ...g,
    items: g.items.filter((it) => !(market === "primary" && it.secondaryOnly)
      && !(market === "secondary" && it.primaryOnly)),
  }));
}
