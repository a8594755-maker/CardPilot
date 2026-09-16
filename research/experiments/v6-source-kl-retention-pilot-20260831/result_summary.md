# v6 source-KL retention result

Decision: RETENTION_GATE_NOT_PASSED.

265993new physical training hands;245760new internal evaluation hands;16clean child exits. Full raw/counter/finite-weight/frozen/source review passed. No old control promotion or Slumbot qualification.

| Contrast |bb/100|95%CI|Six-contrast adjusted CI|
|---|---:|---|---|
|treatment-source anchor0|+56.9747|[5.9294098516211164, 108.02005303900388]|[-11.734804764644721, 125.68426765526972]|
|treatment-source anchor1|+191.7971|[126.01461368932556, 257.57950252161197]|[103.25062318303515, 280.34349302790235]|
|treatment-source anchor2|+273.9153|[197.23676348386445, 350.5938029223855]|[170.70219015783437, 377.12837624841563]|
|treatment-source anchor3|+62.6292|[-16.984274677814263, 142.24257545906426]|[-44.53447091203122, 169.7927716932812]|
|treatment-source anchor4|+99.9177|[-9.265331822917048, 209.10078104166706]|[-47.04808802986838, 246.88353724861838]|
|heldout treatment-control mean|-43.3179|[-129.4687022339389, 42.83289901128265]|[-159.28115485543438, 72.64535163277813]|

Training seeds match the old control,not necessarily its asynchronous trajectories. These heldout anchors are not wholly unseen families; one training-seed intervention is not a multi-seed causal proof.
