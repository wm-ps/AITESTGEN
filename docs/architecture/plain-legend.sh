#!/bin/sh
# Archify's legend always says Frontend/Database; swap in plain words for slides.
# Rerun after every `archify deliver` of vantage-product-flow.architecture.json.
f="${1:-$(dirname "$0")/vantage-product-flow.html}"
sed -i \
 -e 's|y="533" class="t-primary" font-size="9" font-weight="600">Legend</text>|y="528" class="t-primary" font-size="11" font-weight="600">Key</text>|' \
 -e 's|<rect x="40" y="538" width="14" height="9"|<rect x="40" y="536" width="18" height="12"|' \
 -e 's|<text x="60" y="546" class="t-muted" font-size="8">Frontend</text>|<text x="66" y="546" class="t-muted" font-size="11">You do this</text>|' \
 -e 's|<rect x="144" y="538" width="14" height="9"|<rect x="190" y="536" width="18" height="12"|' \
 -e 's|<text x="164" y="546" class="t-muted" font-size="8">Database</text>|<text x="216" y="546" class="t-muted" font-size="11">Vantage does it for you</text>|' \
 -e 's|Green box = Vantage does it for you|Purple box = Vantage does it for you|' \
 -e 's|green boxes Vantage does for you|purple boxes Vantage does for you|' \
 "$f"
