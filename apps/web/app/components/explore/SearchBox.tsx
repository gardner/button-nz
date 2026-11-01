"use client";

import { useEffect, useId, useRef, useState } from "react";

import { type Address, MIN_QUERY, searchAddresses } from "@/lib/sites";

const PAUSE_MS = 250;

/** Find any New Zealand address: LINZ's addresses, asked for once the
 * typing pauses, chosen by click or with the arrow keys and Enter. */
export function SearchBox({
  onPick,
  autoFocus = false,
}: {
  onPick: (address: Address) => void;
  autoFocus?: boolean;
}) {
  const listId = useId();
  const [query, setQuery] = useState("");
  const [found, setFound] = useState<Address[] | null>(null);
  const [active, setActive] = useState(-1);
  const [problem, setProblem] = useState<string | null>(null);
  const asked = useRef(0);
  const [picked, setPicked] = useState<string | null>(null); // the address chosen, as shown

  const searching = query.trim().length >= MIN_QUERY && query !== picked;
  useEffect(() => {
    if (!searching) return;
    const ask = ++asked.current;
    const timer = setTimeout(() => {
      searchAddresses(query).then(
        (addresses) => {
          if (ask !== asked.current) return; // a later search has been asked
          setProblem(null);
          setFound(addresses);
          setActive(-1);
        },
        (e: Error) => {
          if (ask !== asked.current) return;
          setProblem(e.message);
          setFound(null); // no suggestions left from an older search
        },
      );
    }, PAUSE_MS);
    return () => clearTimeout(timer);
  }, [query, searching]);

  // The list lies in the panel's flow, so the panel may need to scroll to it.
  useEffect(() => {
    if (active < 0) return;
    document
      .getElementById(`${listId}-${active}`)
      ?.scrollIntoView({ block: "nearest" });
  }, [active, listId]);

  function pick(address: Address) {
    asked.current++; // whatever is on its way is no longer wanted
    setPicked(address.address);
    setQuery(address.address);
    setFound(null);
    onPick(address);
  }

  function keyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    if (!open || !found?.length) return;
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      const step = event.key === "ArrowDown" ? 1 : -1;
      setActive((a) => (a + step + found.length) % found.length);
    } else if (event.key === "Enter" && active >= 0) {
      event.preventDefault();
      pick(found[active]);
    } else if (event.key === "Escape") {
      setFound(null);
    }
  }

  const open = searching && found !== null;
  return (
    <div>
      <input
        role="combobox"
        aria-label="Find an address"
        aria-expanded={open}
        aria-controls={listId}
        aria-activedescendant={active >= 0 ? `${listId}-${active}` : undefined}
        autoComplete="off"
        autoFocus={autoFocus}
        value={query}
        onChange={(e) => {
          asked.current++; // an answer still on its way is for other text
          setQuery(e.target.value);
          setFound(null); // and so are the suggestions shown
          setProblem(null); // and why the last search failed
          setPicked(null); // edited, even back to the pick, it is asked again
        }}
        onKeyDown={keyDown}
        placeholder="Type any New Zealand address…"
        className="w-full rounded-2xl border border-white/20 bg-white/95 px-5 py-4 text-lg text-zinc-900 shadow-2xl outline-none placeholder:text-zinc-500 focus:ring-4 focus:ring-emerald-400/60"
      />
      {problem && (
        <p
          role="alert"
          className="mt-2 rounded-lg bg-red-900/80 px-3 py-2 text-sm text-white"
        >
          Couldn&apos;t search: {problem}
        </p>
      )}
      {open && (
        <ul
          id={listId}
          role="listbox"
          aria-label="Addresses"
          className="mt-2 w-full overflow-hidden rounded-2xl bg-white text-zinc-900 shadow-2xl"
        >
          {found.length === 0 ? (
            <li className="px-5 py-3 text-zinc-500">
              No address matches &ldquo;{query}&rdquo;.
            </li>
          ) : (
            found.map((a, i) => (
              <li
                key={a.id}
                id={`${listId}-${i}`}
                role="option"
                aria-selected={i === active}
                onMouseDown={(e) => e.preventDefault()} // keep the focus in the box
                onClick={() => pick(a)}
                className={`cursor-pointer px-5 py-3 ${i === active ? "bg-emerald-100" : "hover:bg-zinc-100"}`}
              >
                <span className="font-medium">{a.address}</span>
              </li>
            ))
          )}
        </ul>
      )}
    </div>
  );
}
