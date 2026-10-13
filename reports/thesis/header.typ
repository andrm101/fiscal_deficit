#show table: set text(size: 8.5pt)
#set table(inset: (x: 4pt, y: 3pt))
// single-sided document: orange-book starts chapters on the next odd page; start them on the next page
#show pagebreak.where(to: "odd"): it => pagebreak()
