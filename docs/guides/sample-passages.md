# Sample camera catalogue passages

Actual records generated from the bundled catalogue by
[`make_passages`](../../app/catalog.py), using the pinned MiniLM tokenizer and the
default 240-token indexed-text budget / 32-token overlap. Generated 2026-09-15.
This is a documentation snapshot, not an input to the seed loader.

## What to look for

- One product can produce several indexed documents, each with the same `product_id`.
- `field` identifies the original title, description, or bullet-point field.
- `text` is the chunk itself. `start` is inclusive and `end` exclusive, measured
  in characters of the **cleaned source field**, not the raw HTML or token positions.
- `search_text` adds bounded title, brand and colour context to the chunk.
  This is what BM25 searches and what the embedding model encodes.
- Redis additionally stores an `embedding` array of 384 floats for each passage.
  Those vectors are omitted here so the examples remain readable.
- Splits follow token budgets, not topic labels or sentence boundaries. Overlap
  repeats some text so details near a boundary remain searchable.

The first example is a short camera listing. The second is an accessory with a
longer description, demonstrating overlapping chunks. All passages for both
products are included, with their complete `text` and `search_text` values.

## Sony Alpha ZV-E10 - APS-C Interchangeable Lens Mirrorless Vlog Camera - White

Product ID: `B09BBKVMCD` · 2 passages.

The source has no description; no description passage is invented.

| Passage | Source field | Character range | Indexed tokens* |
|---|---|---|---|
| `us:B09BBKVMCD:0` | `product_title` | 0–77 | 47 |
| `us:B09BBKVMCD:1` | `product_bullet_point` | 0–340 | 105 |

*Token counts exclude model special tokens.

### Passage `us:B09BBKVMCD:0`

```json
{
  "passage_id": "us:B09BBKVMCD:0",
  "field": "product_title",
  "text": "Sony Alpha ZV-E10 - APS-C Interchangeable Lens Mirrorless Vlog Camera - White",
  "start": 0,
  "end": 77,
  "product_id": "B09BBKVMCD",
  "title": "Sony Alpha ZV-E10 - APS-C Interchangeable Lens Mirrorless Vlog Camera - White",
  "brand": "Sony",
  "color": "White",
  "search_text": "Sony Alpha ZV-E10 - APS-C Interchangeable Lens Mirrorless Vlog Camera - White Sony White. Sony Alpha ZV-E10 - APS-C Interchangeable Lens Mirrorless Vlog Camera - White"
}
```

### Passage `us:B09BBKVMCD:1`

```json
{
  "passage_id": "us:B09BBKVMCD:1",
  "field": "product_bullet_point",
  "text": "Large 24.2MP APS-C Exmor CMOS Sensor and fast BIONZ X processor 4K Movie oversampled from 6k w/ full pixel readout, no pixel binning Product Showcase Setting transitions focus from face to object Background Defocus button instantly toggles between defocus effect on/off Easy live streaming w/ single USB cable and no extra hardware/software",
  "start": 0,
  "end": 340,
  "product_id": "B09BBKVMCD",
  "title": "Sony Alpha ZV-E10 - APS-C Interchangeable Lens Mirrorless Vlog Camera - White",
  "brand": "Sony",
  "color": "White",
  "search_text": "Sony Alpha ZV-E10 - APS-C Interchangeable Lens Mirrorless Vlog Camera - White Sony White. Large 24.2MP APS-C Exmor CMOS Sensor and fast BIONZ X processor 4K Movie oversampled from 6k w/ full pixel readout, no pixel binning Product Showcase Setting transitions focus from face to object Background Defocus button instantly toggles between defocus effect on/off Easy live streaming w/ single USB cable and no extra hardware/software"
}
```

## Godox TT350N TTL Flash Speedlite 2.4G Wireless GN36 1/8000s HSS for Nikon D800 D700 D7100 D7000 D5200 D5100 D810 D750 D610 DSLR Camera

Product ID: `B06VTYWCRH` · 5 passages.

| Passage | Source field | Character range | Indexed tokens* |
|---|---|---|---|
| `us:B06VTYWCRH:0` | `product_title` | 0–134 | 107 |
| `us:B06VTYWCRH:1` | `product_description` | 0–642 | 237 |
| `us:B06VTYWCRH:2` | `product_description` | 539–997 | 201 |
| `us:B06VTYWCRH:3` | `product_bullet_point` | 0–547 | 237 |
| `us:B06VTYWCRH:4` | `product_bullet_point` | 405–817 | 182 |

*Token counts exclude model special tokens.

### Passage `us:B06VTYWCRH:0`

```json
{
  "passage_id": "us:B06VTYWCRH:0",
  "field": "product_title",
  "text": "Godox TT350N TTL Flash Speedlite 2.4G Wireless GN36 1/8000s HSS for Nikon D800 D700 D7100 D7000 D5200 D5100 D810 D750 D610 DSLR Camera",
  "start": 0,
  "end": 134,
  "product_id": "B06VTYWCRH",
  "title": "Godox TT350N TTL Flash Speedlite 2.4G Wireless GN36 1/8000s HSS for Nikon D800 D700 D7100 D7000 D5200 D5100 D810 D750 D610 DSLR Camera",
  "brand": "GODOX",
  "color": "",
  "search_text": "Godox TT350N TTL Flash Speedlite 2.4G Wireless GN36 1/8000s HSS for Nikon D800 D700 D7100 D7000 D5200 D5100 D8. Godox TT350N TTL Flash Speedlite 2.4G Wireless GN36 1/8000s HSS for Nikon D800 D700 D7100 D7000 D5200 D5100 D810 D750 D610 DSLR Camera"
}
```

### Passage `us:B06VTYWCRH:1`

```json
{
  "passage_id": "us:B06VTYWCRH:1",
  "field": "product_description",
  "text": "Specification: Guide No.(1/1 out@105mm): 36(m ISO 100) Flash Duration: 1/350 to 1/20000s Flash Coverage: 24-105mm, Auto Zoom/Manual Zoom Swinging/Tilting: 0 to 270° Horizontally and -7° to 90° Vertically Exposure control system: TTL Autoflash and Manual flash Flash exposure compensation(FEC): Manual, FEB:±3 stops in 1/3 stop increments(Manual FEC.) Sync mode: HSS 1/8000s, first-curtain sync, and second curtain sync Multi flash: Provided(up to 90 times,99Hz) Wireless flash function: Master, Slave, Off Controllable slave groups: 3(A,B and C) Transmission range: < 30m Channel: 16(1-16) Auto Focus Assit Beam Effective Range: Center 0.6-4m",
  "start": 0,
  "end": 642,
  "product_id": "B06VTYWCRH",
  "title": "Godox TT350N TTL Flash Speedlite 2.4G Wireless GN36 1/8000s HSS for Nikon D800 D700 D7100 D7000 D5200 D5100 D810 D750 D610 DSLR Camera",
  "brand": "GODOX",
  "color": "",
  "search_text": "Godox TT350N TTL Flash Speedlite 2.4G Wireless GN36 1/8000s HSS for Nikon D800 D700 D7100 D7000 D5200 D5100 D8. Specification: Guide No.(1/1 out@105mm): 36(m ISO 100) Flash Duration: 1/350 to 1/20000s Flash Coverage: 24-105mm, Auto Zoom/Manual Zoom Swinging/Tilting: 0 to 270° Horizontally and -7° to 90° Vertically Exposure control system: TTL Autoflash and Manual flash Flash exposure compensation(FEC): Manual, FEB:±3 stops in 1/3 stop increments(Manual FEC.) Sync mode: HSS 1/8000s, first-curtain sync, and second curtain sync Multi flash: Provided(up to 90 times,99Hz) Wireless flash function: Master, Slave, Off Controllable slave groups: 3(A,B and C) Transmission range: < 30m Channel: 16(1-16) Auto Focus Assit Beam Effective Range: Center 0.6-4m"
}
```

### Passage `us:B06VTYWCRH:2`

```json
{
  "passage_id": "us:B06VTYWCRH:2",
  "field": "product_description",
  "text": "and C) Transmission range: < 30m Channel: 16(1-16) Auto Focus Assit Beam Effective Range: Center 0.6-4m/Periphery: 0.6-2.5m Power Supply: Ni-MH batteries(recommended) or 2* LR6 Alkaline batteries Recycle time: Approx. 0.1-2.2s(eneloop Ni-MH batteries) Full power flahes: Approx. 210(2500mA Ni-MH batteries) Dimension: 140*62*38mm Net weight: 200g Packge Included: 1 x TT350N Mini Flash 1 x Softbox 1 x Protective Bag 1 x Mini Stand 1 x CEARI MicroFiber Cloth",
  "start": 539,
  "end": 997,
  "product_id": "B06VTYWCRH",
  "title": "Godox TT350N TTL Flash Speedlite 2.4G Wireless GN36 1/8000s HSS for Nikon D800 D700 D7100 D7000 D5200 D5100 D810 D750 D610 DSLR Camera",
  "brand": "GODOX",
  "color": "",
  "search_text": "Godox TT350N TTL Flash Speedlite 2.4G Wireless GN36 1/8000s HSS for Nikon D800 D700 D7100 D7000 D5200 D5100 D8. and C) Transmission range: < 30m Channel: 16(1-16) Auto Focus Assit Beam Effective Range: Center 0.6-4m/Periphery: 0.6-2.5m Power Supply: Ni-MH batteries(recommended) or 2* LR6 Alkaline batteries Recycle time: Approx. 0.1-2.2s(eneloop Ni-MH batteries) Full power flahes: Approx. 210(2500mA Ni-MH batteries) Dimension: 140*62*38mm Net weight: 200g Packge Included: 1 x TT350N Mini Flash 1 x Softbox 1 x Protective Bag 1 x Mini Stand 1 x CEARI MicroFiber Cloth"
}
```

### Passage `us:B06VTYWCRH:3`

```json
{
  "passage_id": "us:B06VTYWCRH:3",
  "field": "product_bullet_point",
  "text": "GN36 (m ISO 100,@105mm), 22 steps of power output(1/1-1/128), Support TTL/M/Multi/S1/S2 modes, 24-105mm auto/manual zooming, Approx. 0.1-2.2s recycle time, 210 full power flashes(using 2500mA Ni-MH batteries) Compatible with Nikon Mirrorless Cameras D800 D700 D7100 D7000 D5200 D5100 D5000 D300 D200 D30S D3200 D3100 D3000 D70S D810 D90 D610 D750 etc Support for TTL autoflash, manual flash, multi flash, 1/8000s high speed sync, flash exposure compensation, flash exposure lock, manual focus assist, rear curtain sync etc. With a compact body, 2.",
  "start": 0,
  "end": 547,
  "product_id": "B06VTYWCRH",
  "title": "Godox TT350N TTL Flash Speedlite 2.4G Wireless GN36 1/8000s HSS for Nikon D800 D700 D7100 D7000 D5200 D5100 D810 D750 D610 DSLR Camera",
  "brand": "GODOX",
  "color": "",
  "search_text": "Godox TT350N TTL Flash Speedlite 2.4G Wireless GN36 1/8000s HSS for Nikon D800 D700 D7100 D7000 D5200 D5100 D8. GN36 (m ISO 100,@105mm), 22 steps of power output(1/1-1/128), Support TTL/M/Multi/S1/S2 modes, 24-105mm auto/manual zooming, Approx. 0.1-2.2s recycle time, 210 full power flashes(using 2500mA Ni-MH batteries) Compatible with Nikon Mirrorless Cameras D800 D700 D7100 D7000 D5200 D5100 D5000 D300 D200 D30S D3200 D3100 D3000 D70S D810 D90 D610 D750 etc Support for TTL autoflash, manual flash, multi flash, 1/8000s high speed sync, flash exposure compensation, flash exposure lock, manual focus assist, rear curtain sync etc. With a compact body, 2."
}
```

### Passage `us:B06VTYWCRH:4`

```json
{
  "passage_id": "us:B06VTYWCRH:4",
  "field": "product_bullet_point",
  "text": "1/8000s high speed sync, flash exposure compensation, flash exposure lock, manual focus assist, rear curtain sync etc. With a compact body, 2.4G wireless transmission and 30 meters further transmission As a mater unit, TT350N can control the AD600, AD600M, AD360II-C AD360II-N, V860IIN, V850II, TT685N, TT600 speedlite As a slave unit, TT350N can be controlled by X1T-N, V860II-N, V850II, TT685N, TT600 speedlite",
  "start": 405,
  "end": 817,
  "product_id": "B06VTYWCRH",
  "title": "Godox TT350N TTL Flash Speedlite 2.4G Wireless GN36 1/8000s HSS for Nikon D800 D700 D7100 D7000 D5200 D5100 D810 D750 D610 DSLR Camera",
  "brand": "GODOX",
  "color": "",
  "search_text": "Godox TT350N TTL Flash Speedlite 2.4G Wireless GN36 1/8000s HSS for Nikon D800 D700 D7100 D7000 D5200 D5100 D8. 1/8000s high speed sync, flash exposure compensation, flash exposure lock, manual focus assist, rear curtain sync etc. With a compact body, 2.4G wireless transmission and 30 meters further transmission As a mater unit, TT350N can control the AD600, AD600M, AD360II-C AD360II-N, V860IIN, V850II, TT685N, TT600 speedlite As a slave unit, TT350N can be controlled by X1T-N, V860II-N, V850II, TT685N, TT600 speedlite"
}
```

### Overlap between the first two description passages

Characters 539–642 appear in both:

```text
and C) Transmission range: < 30m Channel: 16(1-16) Auto Focus Assit Beam Effective Range: Center 0.6-4m
```

## Where this fits

`Camera record → make_passages() → search_text → embedding → Redis JSON passage`

Retrieval ranks these passages; the app groups them by `product_id` and keeps
the best-ranked passage for each returned product. See the
[index schema](../../schemas/passages.yaml) and [retrieval architecture](../architecture/search.md).

Source: bundled Amazon ESCI records, revision `7916cdf6ab75a462e77f20ab40428a10923998d5`.
See [dataset provenance and licences](dataset.md).
