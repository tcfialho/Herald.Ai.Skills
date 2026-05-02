from pathlib import Path

from .models import Story
from .stories import list_stories
from .tasks import parse_tasks
from .constants import STATUSES


def print_status(root: Path, active: Story | None = None, next_story: Story | None = None) -> None:
    stories = list_stories(root)
    counts = {status: 0 for status in STATUSES}
    total_tasks = 0
    completed_tasks = 0
    for story in stories:
        counts[story.status] = counts.get(story.status, 0) + 1
        for task in parse_tasks(story.body):
            total_tasks += 1
            if task.status == "completed":
                completed_tasks += 1

    print("NEXUS STATUS")
    print(f"Root: {root}")
    print("Stories: " + " ".join(f"{status}={counts.get(status, 0)}" for status in STATUSES))
    print(f"Story progress: {counts.get('DONE', 0)}/{len(stories)} done")
    print(f"Task progress: {completed_tasks}/{total_tasks} complete")
    if active:
        tasks = parse_tasks(active.body)
        completed = sum(1 for task in tasks if task.status == "completed")
        print(f"Active story: {active.story_id} {active.title}")
        print(f"Active owner: {active.meta.get('owner') or '-'}")
        print(f"Current task: {active.meta.get('current_task') or '-'}")
        print(f"Active progress: {completed}/{len(tasks)} tasks")
        print(f"Lease until: {active.meta.get('lease_until') or '-'}")
    elif next_story:
        print(f"Next story: {next_story.story_id} {next_story.title}")
    else:
        ready = [story for story in stories if story.status == "READY"]
        print(f"Next story: {ready[0].story_id + ' ' + ready[0].title if ready else '-'}")
