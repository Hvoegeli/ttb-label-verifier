# User Flow

## Primary Flow

```
+------------------+      +-------------------+      +------------------------+
|  1. Open app     |      |  2. Upload label  |      |  3. (optional) attach  |
|  GET /           | ---> |  choose image     | ---> |  mock application JSON  |
|  see upload page |      |  file             |      |  for match check       |
+------------------+      +-------------------+      +------------------------+
                                                                |
                                                                v
+--------------------------------------------------------------------------+
|  4. Submit  ->  POST /verify                                             |
|     validate image -> Claude vision extract -> rule engine -> verdict     |
|     target: under 5 seconds, single loading indicator                     |
+--------------------------------------------------------------------------+
                                                                |
                                                                v
+--------------------------------------------------------------------------+
|  5. Result page                                                          |
|     +----------------------------+   +-----------------------------+      |
|     |  uploaded label image      |   |  OVERALL: PASS / FAIL /      |     |
|     |                            |   |  NEEDS REVIEW (big, color)   |     |
|     +----------------------------+   +-----------------------------+      |
|     Per field rows:                                                       |
|       Brand name        OK     "matches application"                      |
|       Class/type        OK     27 CFR 5.143                               |
|       Alcohol content   OK     27 CFR 5.65                                |
|       Net contents      OK     27 CFR 5.203 (750 mL authorized)           |
|       Govt warning      FAIL   27 CFR 16.21 (sentence 2 missing)          |
+--------------------------------------------------------------------------+
```

The agent reads the overall verdict first, then scans the colored rows for anything that is not OK. Each problem row names the rule so the agent can act or override with judgment.

## API Endpoints

### GET /
Serves the upload page. No parameters.

### POST /verify
Request (multipart form):
- `image` — the label image file (JPG or PNG), required
- `application` — optional JSON text or file with the mock application fields (brand, class/type, alcohol content, net contents)

Response: rendered HTML result page. The same logic returns structured data internally so the result can later be exposed as JSON for batch mode.

Result shape (internal):
```json
{
  "overall": "FAIL",
  "fields": [
    {
      "name": "net_contents",
      "value": "750 mL",
      "status": "OK",
      "reason": "Authorized standard of fill",
      "citation": "27 CFR 5.203"
    },
    {
      "name": "government_warning",
      "value": "GOVERNMENT WARNING: (1) ...",
      "status": "FAIL",
      "reason": "Second required sentence is missing",
      "citation": "27 CFR 16.21"
    }
  ],
  "match": {
    "brand_name": "MATCH (normalized)",
    "alcohol_content": "MATCH"
  }
}
```

### GET /healthz
Liveness check for the host. Returns `{"status": "ok"}`.

## Example Queries

| Uploaded label | Expected result | Expected reason |
| --- | --- | --- |
| Compliant bourbon (sample label) | PASS | All mandatory fields present and valid |
| Warning in title case "Government Warning" | FAIL | 27 CFR 16.22 requires capitals on "GOVERNMENT WARNING:" |
| Net contents "800 mL" | FAIL | 27 CFR 5.203: not an authorized standard of fill |
| Only "90 Proof", no percent by volume | FAIL | 27 CFR 5.65: percent alcohol by volume is mandatory |
| Warning missing the second sentence | FAIL | 27 CFR 16.21: statement must be verbatim and complete |
| Blurry, unreadable photo | NEEDS REVIEW | Low extraction confidence; request a better image |
| Brand "STONE'S THROW" vs application "Stone's Throw" | MATCH | Brand compared after normalization |
