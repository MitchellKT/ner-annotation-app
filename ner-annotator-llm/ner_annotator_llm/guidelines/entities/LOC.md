# LOC — A physical or geopolitical place.

## What counts as a LOC entity
- Continents, countries, regions, cities, neighbourhoods, addresses,
  buildings, landmarks, rivers, mountains, planets.
- One entity per place: "New York", "the city" and "there" referring to
  it are one entity.
- A place name used as an organisation or a team ("Washington announced
  new sanctions", "London beat Paris 2-0") is ORG, not LOC.
- A place name inside an organisation's name is still its own LOC mention
  when it refers to the place: "America" in "Bank of America" — annotate
  the nested span, and mark it `implicit`.

## What counts as a mention
- Names, descriptive references ("the capital", "the island") and
  pronouns/adverbs that refer to the place ("it", "there").
- Adjectival forms ("French", "Parisian") are mentions of the place when
  they refer to it; mark them `implicit`.
- Take the full name ("Mount Vernon", "New South Wales"), without the
  preposition ("in Hawaii" -> "Hawaii").

## Flags
- `relative`: the place is identified only through a relation — "the
  town where she grew up", "his home country".
- `implicit`: the place is named but in a modifier or background role —
  "a Paris-based photographer", "the Berlin office".
