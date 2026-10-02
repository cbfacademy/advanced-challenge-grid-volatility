# Challenge: Trade the GB Power Market

**You are a power trader. You have 5 hours. Build a strategy, prove it works.**

Every morning, traders at every UK energy company sit down and ask the same question: *what will electricity be worth tomorrow, and how confident am I?* They look at the weather, at how much wind is forecast, at how much demand is expected — and they make decisions based on this.

That's your job today. You get real GB market data covering 2016 to now, and a set of trading rules. What you do with it is up to you.

---

## How the market works (90 seconds)

Electricity is bought and sold for specific slices of time on a specific day. Buy "3pm tomorrow" and you're buying power delivered between 15:00 and 15:30 tomorrow.

There are three prices in play, and they are prices for the *same* electricity, set at three different moments:

| | When it's set | Time slices | Column |
|---|---|---|---|
| **Hourly auction** | 09:00 the day before delivery | 1 hour | `da_hr_epex_price` |
| **Half-hourly auction** | 15:00 the day before delivery | 30 min | `da_hh_epex_price` |
| **Cashout** | After delivery — the final settlement price | 30 min | `cashout_price` |

The hourly auction trades in **whole hours**. The half-hourly auction and cashout work in **half-hours**. So the market gets finer-grained as delivery approaches.

> **Important:** if you buy 10MW for the 15:00–16:00 hour in the hourly auction, you now hold **10MW for 15:00–15:30 and 10MW for 15:30–16:00** — the same size in both halves. You cannot buy "more in the second half" at 9am. That's what the 3pm auction is for.

---

## Your trading rules

For every hour of the delivery day:

1. **09:00 (day before)** — take a position in the hourly auction. One number per hour.
2. **15:00 (day before)** — *optionally* adjust your position in the half-hourly auction. Now you can set each half-hour separately. **Skipping this auction entirely is fine** — do nothing and your 9am position simply carries through to cashout.
3. **After delivery** — whatever you're still holding is closed out at the **cashout price**.

**The one hard rule: every position must be between −25MW and +25MW.** That applies at both auctions, in every hour.

- **Positive (long)** = you've bought power. You profit if the price goes **up**.
- **Negative (short)** = you've sold power you don't yet hold. You profit if the price goes **down**.
- **Zero** = you're flat. Always allowed, and "don't trade" is a legitimate, defensible decision.

You can be long one hour and short the next. You can go long at 9am and flip to short at 3pm if the price moves against you.

**However, we are also judging you on any new ideas. So if you have ideas how you would manage positions in alternative ways (to delivery), you should pitch them!**

### What you're actually betting on

For each half-hour, with `X` = your 9am position and `Y` = what you hold after 3pm:

```
profit = 0.5 × [  X × (HH_price − HR_price)  +  Y × (cashout − HH_price)  ]
```

(the `0.5` converts MW to MWh over a half-hour, giving £)

Read it carefully, because it tells you the whole story:

- Your **9am position** profits when the half-hourly auction comes in **above** the hourly auction.
- Your **final position** profits when cashout comes in **above** the half-hourly auction.

Negative positions need no special handling — the formula does the work. Short 25MW into a price that falls, and the maths gives you a profit automatically.

Two separate decisions. They need two separate opinions — and they are *not* equally risky. Find out which is which before you size up.

---

## The data

See [`README.md`](README.md) for the full dictionary. In short:

- **`market_prices.parquet`** — the three prices above, plus traded volumes. This is your scoreboard.
- **`fuel_prices.xlsx`** — gas, coal and carbon prices, and what they imply about the cost of generating power. **Daily**, 2016 to now. **Available at every decision point** — use it freely at both auctions. See below.
- **`3rd Party Forecasts/`** — demand, generation by fuel type, wind, solar, interconnectors, weather-model output. **All of these were available before the 9am auction on the day before delivery.** One row per delivery period, no revisions. You can use them at either decision point without worrying about whether you'd have had them.
- **`3rd Party Forecasts/Elexon Forecasts/`** — raw feeds straight off the Elexon API. These are the exception: **continuously updated, right through to delivery.** **Handle with care** (see below).

That contrast matters. The third-party forecasts are a fixed, single snapshot taken before you place your first trade — simple and safe. The Elexon feeds keep moving all day, which makes them richer and far more dangerous.

**You do not have to use the forecasts.** Genuinely valid strategies include:

- Prices only — sit out the hourly auction entirely, look at where it settled, then take a view at 3pm.
- Wind forecast only.
- Solar forecast only.
- Fuel prices only — is power cheap or expensive against the cost of making it?
- Everything, in a model.

A simple strategy you understand and can defend beats a complex one you can't.

### Why fuel prices matter

Here's the single most useful idea in power trading: **most of the time, the price of electricity is set by the cost of running a gas power station.** When demand needs that last gas plant to switch on, the plant will only run if the power price covers its fuel and carbon costs — so that cost becomes the price.

That cost has a name: **SRMC**, short-run marginal cost. We've calculated it for you — `UK CCGT SRMC (£/MWh)` is what it costs a typical gas plant to produce 1MWh on that day, given gas and carbon prices. Think of it as the **fair value** of power.

So you have a reference point. If the market is trading well below SRMC, something unusual is going on — probably a lot of wind or solar pushing gas out of the mix. Well above, and the system is tight. That gap between market price and fair value is a signal, and it's a very accessible one.

The file also gives you the raw ingredients — `NBP Gas Curve` (UK gas), `TTF Gas Curve` (European gas), `Coal API2`, and carbon (`UKA`, `UK CPS`, `EUA`) — plus the same SRMC calculation at three different plant efficiencies, since not every gas plant is equally efficient.

Three practical notes. First, **you can use this at any stage** — at the 9am auction, at the 3pm auction, for any delivery day. There's no availability trap here, so don't spend time building one. Second, it's **daily**, while you trade half-hours — so it tells you where the whole *day* should sit, not which half-hour within it is expensive. It pairs naturally with a separate signal for the shape of the day. Third, it's an `.xlsx`, not a parquet, and it isn't laid out as tidily as the other files. Look at it before you load it.

---

## One strategy, or several?

Nothing says you need a single strategy. You could build three or four simple, independent ones — a wind rule, a demand rule, a time-of-day rule — and run them side by side as a **portfolio**, splitting your position limit between them.

This is what real trading desks do, and the reason is diversification: when your strategies make mistakes for *different* reasons, their bad days don't all land on the same day. The ups and downs partly cancel out, and your returns get smoother even if your total profit doesn't get bigger. Smoother is worth a lot — it's the difference between a desk that survives a bad month and one that doesn't.

So it's a real question, and we'd love to see a team answer it with evidence: **are several simple strategies better than one clever one?** You could test it directly — build a few simple rules, measure each alone, then measure them combined, and compare not just the profit but how violent the ride was.

It's also the safer way to spend your time. Three simple rules are three separate small problems you can divide between you and finish. One clever model is a single big problem that is either done or it isn't — and at 4.30pm, "isn't" is a very bad place to be.

**And you don't have to trade at all.** 0MW across the board is a legitimate submission if you can show us *why* — that you looked, measured, found no edge you trusted, and declined to bet. That is a real conclusion that real traders reach, and it will score far better than a strategy you can't justify.

---

## Two things that will catch you out

**1. Timestamps.** Pay very close attention to them. Every decision you make happens at a specific moment, and you may only use information that existed *at that moment*. A strategy that accidentally peeks at the future will look fantastic and be worthless. Check your timestamps, then check them again.

One exception, to save you worrying about it: **the fuel prices are safe to use at every stage.** You can use them freely at the 9am auction and at the 3pm auction — no lagging, no availability caveats. Same for the third-party forecasts. It's the Elexon feeds where this matters.

**2. The Elexon files.** These are raw, and they are a different shape to everything else.

They are **continuously updating forecasts**. Elexon re-publishes its view of a delivery period over and over as it approaches — before the 9am auction, between the 9am and 3pm auctions, after 3pm, and right up to delivery itself. So a single delivery period appears **many times**, each row carrying the `publishTime` that tells you when that version existed. Some of those rows were published *after* delivery.

That's genuinely valuable: it's the only data here that tells you how the outlook **changed** between your two decision points. A forecast that moved sharply between 9am and 3pm is information you could have traded on.

It is also the most dangerous data in the pack. Only the rows published before your decision time were available to you, and the files run to tens of millions of rows each.

**A hint on why they're so big.** Four of these feeds carry a `boundary` column with **18 different values**, and the same delivery period is reported separately for every one of them. A boundary is a dividing line across the transmission network — the grid isn't one big pool, and power can only flow across each line up to a limit.

This means a row is **not** unique on delivery period and `publishTime` alone. Ignore the boundary and you'll silently get eighteen copies of everything. Pick one and the file gets eighteen times smaller, which is most of your performance problem solved in a single filter.

Which one? **`N` is the national total** — the sensible default. But also **try `B6`**: it's the Scotland–England interface, and a lot of GB wind sits on the far side of it. When Scotland generates more wind than that boundary can carry south, interesting things happen to prices. We'll leave the rest to you.

To see where these zones actually are on the map, Elexon publish one here: [**GB Transmission System Boundary Zone Map**](https://www.elexon.co.uk/bsc/documents/data/operational-data/gb-transmission-system-boundary-zone-map/). Worth two minutes — the geography makes the boundary codes click, and it may give you ideas about which zones matter for wind, demand, or solar.

**So triage it early.** Spend twenty minutes — no more — working out how complex these files really are and what it would cost you to use them properly. Then make a deliberate call: is the payoff worth the hours, with the clock running? Deciding *not* to use them, for a stated reason, is a valid engineering decision. Half-using them and quietly leaking post-delivery data into your backtest is the worst outcome available to you.

Rigorous handling of publication times is one of the most heavily rewarded things in this challenge.

---

## Benchmark yourself

A number with nothing to compare it to means nothing. Report your strategy against all three of these:

- **Do nothing** — 0MW everywhere. Profit of exactly £0.
- **Always maximum long** — +25MW at 9am, held to cashout.
- **Always maximum short** — −25MW at 9am, held to cashout.

**That's the bar.** A strategy that makes money but can't beat a fixed position held blindly for six months hasn't earned anything. If you can't beat the best constant benchmark, say so plainly — we'd far rather see that than a number with no context. And if one of them is profitable, work out *why*, and share that with us.

---

## Some trading tips

Making the most money is **not** the whole challenge.

**On position sizing:** ±25MW is your limit, not your default. We want to know why you chose the size *and the direction* you chose. Does a stronger signal earn a bigger position? What happens in an hour you're unsure about — do you halve it, or go flat? Sizing that reflects genuine confidence scores well; slamming the maximum into every hour scores poorly, even if it happens to make money.

**On risk:** total profit hides everything. Show us your biggest daily and weekly drops, how often you made a profit versus the size of those gains, and what your deepest drawdown looked like. A smaller, steady return may well outperform a larger, highly volatile one.

---

## You have limited time

Aim to have finished by the feature freeze at 16:30. A suggested shape:

**Divide and conquer.**

**Beware the rabbit hole.** 

**Good luck. Trade well.**
