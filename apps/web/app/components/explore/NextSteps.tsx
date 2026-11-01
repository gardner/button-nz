const BDC =
  "https://bullerdc.govt.nz/property-rates-and-building/building-and-building-consents/granny-flat-building-consent-exemption/";
const SUPPLIERS =
  "https://github.com/gardner/button-nz/blob/master/docs/suppliers.md";

/** What the granny-flat exemption asks of the owner next, from the council's
 * page and the sourced research on who serves Reefton. */
export function NextSteps() {
  return (
    <section className="flex flex-col gap-1 text-sm">
      <h3 className="font-medium">Next steps</h3>
      <ol className="list-decimal pl-5">
        <li>
          A project information memorandum (PIM) from{" "}
          <a href={BDC} target="_blank" rel="noreferrer" className="underline">
            Buller District Council
          </a>{" "}
          before work starts.
        </li>
        <li>
          A licensed designer to design it, and a licensed building practitioner
          to build or supervise it.
        </li>
        <li>
          A ground test before choosing foundations; poor ground needs a
          geotechnical investigation and an engineer.
        </li>
        <li>
          Certifying plumbers, drainlayers and electricians, who give you their
          records; within 20 working days of completion you give the council the
          final plans and every record and certificate.
        </li>
      </ol>
      <a
        href={SUPPLIERS}
        target="_blank"
        rel="noreferrer"
        className="underline"
      >
        Local firms, connections and open questions for the council
      </a>
    </section>
  );
}
