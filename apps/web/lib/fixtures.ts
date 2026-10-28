/** API responses shared by the tests. */

export const JOB = {
  id: "abc123",
  brief: "A small studio.",
  allow_observations: true,
  status: "done",
  created_at: "2026-10-28T09:00:00Z",
  started_at: "2026-10-28T09:00:01Z",
  finished_at: "2026-10-28T09:03:00Z",
  error: null,
  accepted_attempt: 2,
  attempts: [
    {
      number: 1,
      status: "fail",
      feedback: "title_boundary_setback: fail. 0.50 m from the boundary.",
      observations: ["render_contours"],
      files: { "design.png": "/designs/abc123/attempts/1/design.png" },
    },
  ],
};
