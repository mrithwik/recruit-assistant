import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, Briefcase, Plus, SlidersHorizontal } from "lucide-react";
import { useCriteriaStore } from "../stores/criteria-store";
import { useToastStore } from "../stores/toast-store";
import { PageHeader } from "../components/ui/page-header";
import { Card, CardDashed } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Input, Label } from "../components/ui/input";
import { onNumberChange, selectOnFocus } from "../lib/number-input";

export function CriteriaPage() {
  const { criteria, fetchCriteria, addCriterion } = useCriteriaStore();
  const push = useToastStore((s) => s.push);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [weight, setWeight] = useState(1);

  useEffect(() => {
    // This page is the global library (built-in + custom criteria
    // definitions) — no job filter, since which job has which criterion
    // *selected* (enabled/value) lives on the Jobs page, not here.
    fetchCriteria(undefined).catch(() => {});
  }, []);

  async function submit() {
    if (!name.trim()) return;
    try {
      await addCriterion(name, description, weight, null);
      push("Criterion added to the library — enable it per-job from the Job Descriptions page", "success");
      setName("");
      setDescription("");
      setWeight(1);
    } catch (e) {
      push(String(e), "error");
    }
  }

  return (
    <div className="mx-auto max-w-2xl">
      <PageHeader title="Criteria" description="Built-in job-board filters plus anything custom you add." />

      <div className="space-y-6">
        <Card className="p-0">
          <ul className="divide-y divide-zinc-100 dark:divide-zinc-800">
            {criteria.map((c) => (
              <li key={c.id} className="flex items-center justify-between p-3.5 text-sm">
                <div>
                  <p className="flex items-center gap-2 font-medium text-zinc-900 dark:text-white">
                    {c.name}
                    {c.is_builtin && (
                      <span className="rounded-full bg-zinc-100 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-zinc-500 dark:bg-zinc-800 dark:text-zinc-400">
                        Built-in
                      </span>
                    )}
                  </p>
                  <p className="text-zinc-500 dark:text-zinc-400">{c.description}</p>
                </div>
                <span className="shrink-0 rounded-md bg-indigo-50 px-2 py-1 text-xs font-semibold text-indigo-700 dark:bg-indigo-500/10 dark:text-indigo-300">
                  ×{c.weight}
                </span>
              </li>
            ))}
          </ul>
        </Card>

        <CardDashed>
          <div className="mb-3 flex items-center gap-2">
            <SlidersHorizontal size={15} className="text-zinc-400" />
            <h2 className="font-medium text-zinc-900 dark:text-white">Add custom criterion</h2>
          </div>
          <div className="mb-3">
            <Label>Name</Label>
            <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Prior startup experience" />
          </div>
          <div className="mb-3">
            <Label>Description</Label>
            <Input value={description} onChange={(e) => setDescription(e.target.value)} placeholder="Description" />
          </div>
          <div className="mb-4 w-28">
            <Label>Weight</Label>
            <Input type="number" step={0.1} value={weight} onChange={onNumberChange(setWeight)} onFocus={selectOnFocus} />
          </div>
          <Button icon={<Plus size={15} />} onClick={submit}>
            Add criteria
          </Button>
        </CardDashed>

        <Card className="border-dashed border-zinc-200 bg-zinc-50/60 dark:border-zinc-800 dark:bg-zinc-900/40">
          <div className="flex items-start gap-3">
            <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-indigo-50 text-indigo-600 dark:bg-indigo-500/10 dark:text-indigo-400">
              <Briefcase size={15} />
            </div>
            <div>
              <p className="font-medium text-zinc-900 dark:text-white">Enabling criteria and rescanning is per-job</p>
              <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
                This page is the shared library — the criteria every job can choose from. To turn a
                criterion on/off, set its value, or trigger a rescan, open the specific job on the Job
                Descriptions page and use its Criteria and Scan &amp; Match panels.
              </p>
              <Link
                to="/app/jobs"
                className="mt-2 inline-flex items-center gap-1 text-sm font-medium text-indigo-600 hover:underline dark:text-indigo-400"
              >
                Go to Job Descriptions <ArrowRight size={13} />
              </Link>
            </div>
          </div>
        </Card>
      </div>
    </div>
  );
}
