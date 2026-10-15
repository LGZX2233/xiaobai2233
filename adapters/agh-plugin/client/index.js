// client/src/app/Shell.jsx
import { useCallback as useCallback2, useEffect as useEffect3, useMemo as useMemo5, useState as useState13, useSyncExternalStore } from "react";

// client/src/i18n/messages.js
var entries = {
  "navigation.overview": ["Overview", "\u603B\u89C8"],
  "navigation.design": ["Design", "\u8BBE\u8BA1"],
  "navigation.workspace": ["Workspace", "\u5DE5\u4F5C\u533A"],
  "navigation.structure": ["Structure", "\u7ED3\u6784"],
  "navigation.requirements": ["Requirements", "\u9700\u6C42"],
  "navigation.execution": ["Run", "\u6267\u884C"],
  "navigation.permissions": ["Approvals", "\u5BA1\u6279"],
  "navigation.environment": ["Environment", "\u73AF\u5883"],
  "navigation.versions": ["Versions", "\u7248\u672C"],
  "navigation.events": ["Events", "\u4E8B\u4EF6"],
  "navigation.errors": ["Errors", "\u9519\u8BEF"],
  "navigation.documents": ["Docs", "\u6587\u6863"],
  "navigation.skills": ["Skills", "Skill"],
  "navigation.knowledge": ["Knowledge", "\u77E5\u8BC6"],
  "group.project": ["Project", "\u9879\u76EE"],
  "group.run": ["Run", "\u8FD0\u884C"],
  "group.govern": ["Governance", "\u6CBB\u7406"],
  "group.records": ["Records", "\u8BB0\u5F55"],
  "shell.title": ["Project Kernel", "Project Kernel"],
  "shell.refresh": ["Refresh", "\u5237\u65B0"],
  "shell.connected": ["Connected", "\u5DF2\u8FDE\u63A5"],
  "shell.disconnected": ["Offline", "\u672A\u8FDE\u63A5"],
  "shell.asOf": ["Read at", "\u8BFB\u53D6\u81F3"],
  "shell.head": ["Head", "\u6700\u65B0"],
  "shell.completeness": ["Complete", "\u5B8C\u6574\u5EA6"],
  "shell.freshness": ["Fresh", "\u65B0\u9C9C\u5EA6"],
  "shell.watermarkTip": ["Read at: newest commit this read can see. Head: newest commit in the store. Complete and fresh describe the read, not the work.", "\u8BFB\u53D6\u81F3\uFF1A\u672C\u6B21\u8BFB\u53D6\u80FD\u770B\u5230\u7684\u6700\u65B0\u63D0\u4EA4\u3002\u6700\u65B0\uFF1A\u8D26\u672C\u91CC\u6700\u65B0\u7684\u63D0\u4EA4\u3002\u5B8C\u6574\u5EA6\u3001\u65B0\u9C9C\u5EA6\u63CF\u8FF0\u8FD9\u6B21\u8BFB\u53D6\uFF0C\u4E0D\u662F\u5DE5\u4F5C\u6210\u679C\u3002"],
  "shell.gaps": ["Gaps ({count})", "\u7F3A\u53E3\uFF08{count}\uFF09"],
  "shell.history": ["History view #{seq}", "\u5386\u53F2\u89C6\u56FE #{seq}"],
  "shell.current": ["Back to now", "\u56DE\u5230\u5F53\u524D"],
  "shell.sessionRequired": ["Pick a session and turn on the services capability.", "\u5148\u9009\u4E00\u4E2A\u4F1A\u8BDD\uFF0C\u5E76\u5F00\u542F services \u80FD\u529B\u3002"],
  "shell.noMetadata": ["No read info yet", "\u6682\u65E0\u8BFB\u53D6\u4FE1\u606F"],
  "shell.connectionError": ["Cannot read the kernel: {error}", "\u8BFB\u4E0D\u5230\u5185\u6838\uFF1A{error}"],
  "shell.breadcrumb": ["Location", "\u5F53\u524D\u4F4D\u7F6E"],
  "shell.widen": ["Widen", "\u52A0\u5BBD"],
  "shell.narrow": ["Narrow", "\u6536\u7A84"],
  "shell.close": ["Close", "\u5173\u95ED"],
  "source.live": ["Live", "\u5B9E\u65F6"],
  "source.document": ["Document", "\u6587\u6863"],
  "source.derived": ["Derived", "\u6D3E\u751F"],
  "source.preview": ["Design preview", "\u8BBE\u8BA1\u9884\u89C8"],
  "source.liveTip": ["Read from the kernel now", "\u5B9E\u65F6\u8BFB\u53D6\u81EA\u5185\u6838"],
  "source.documentTip": ["Declared in documents on disk, not a runtime reading", "\u6765\u81EA\u78C1\u76D8\u6587\u6863\u7684\u58F0\u660E\uFF0C\u4E0D\u662F\u8FD0\u884C\u8BFB\u6570"],
  "source.derivedTip": ["Worked out in this panel from loaded data, not a kernel reading", "\u9762\u677F\u5BF9\u5DF2\u52A0\u8F7D\u6570\u636E\u7684\u6C47\u603B\uFF0C\u4E0D\u662F\u5185\u6838\u8BFB\u6570"],
  "source.previewTip": ["Example data, not connected to the kernel", "\u793A\u4F8B\u6570\u636E\uFF0C\u5C1A\u672A\u63A5\u5165\u5185\u6838"],
  "common.unknown": ["Unknown", "\u672A\u77E5"],
  "common.none": ["None", "\u6682\u65E0"],
  "common.close": ["Dismiss", "\u6536\u8D77"],
  "common.query": ["Look up", "\u67E5\u8BE2"],
  "common.queryPrompt": ["Enter an ID to look it up.", "\u8F93\u5165\u6807\u8BC6\u540E\u67E5\u8BE2\u3002"],
  "common.status": ["Status", "\u72B6\u6001"],
  "common.details": ["Details", "\u8BE6\u60C5"],
  "common.yes": ["Yes", "\u662F"],
  "common.no": ["No", "\u5426"],
  "common.all": ["All", "\u5168\u90E8"],
  "common.shown": ["{shown} of {total}", "\u663E\u793A {shown} / {total}"],
  "status.loading": ["Loading\u2026", "\u52A0\u8F7D\u4E2D\u2026"],
  "status.unavailable": ["Unavailable", "\u4E0D\u53EF\u7528"],
  "status.noData": ["Nothing recorded yet", "\u6682\u65E0\u8BB0\u5F55"],
  "status.stale": ["Read may be stale or incomplete", "\u8BFB\u53D6\u53EF\u80FD\u8FC7\u671F\u6216\u4E0D\u5B8C\u6574"],
  "status.documentGaps": ["Document data has gaps", "\u6587\u6863\u6570\u636E\u6709\u7F3A\u53E3"],
  "status.completed": ["Completed", "\u5DF2\u5B8C\u6210"],
  "status.failed": ["Failed", "\u5931\u8D25"],
  "status.unknown": ["Unknown", "\u672A\u77E5"],
  "status.running": ["Running", "\u8FD0\u884C\u4E2D"],
  "status.starting": ["Starting", "\u542F\u52A8\u4E2D"],
  "status.cancelled": ["Cancelled", "\u5DF2\u53D6\u6D88"],
  "status.interrupted": ["Interrupted", "\u5DF2\u4E2D\u65AD"],
  "status.pending": ["Waiting for you", "\u5F85\u4F60\u5BA1\u6279"],
  "status.approved": ["Approved", "\u5DF2\u6279\u51C6"],
  "status.rejected": ["Rejected", "\u5DF2\u62D2\u7EDD"],
  "status.expired": ["Expired", "\u5DF2\u8FC7\u671F"],
  "status.prepared": ["Prepared", "\u5DF2\u51C6\u5907"],
  "status.claimed": ["Claimed", "\u5DF2\u8BA4\u9886"],
  "status.applying": ["Applying", "\u5E94\u7528\u4E2D"],
  "status.applied": ["Applied", "\u5DF2\u5E94\u7528"],
  "status.selected": ["Selected", "\u5DF2\u9009\u5B9A"],
  "status.not_checked": ["Not checked", "\u672A\u68C0\u67E5"],
  "status.satisfied": ["Met", "\u5DF2\u6EE1\u8DB3"],
  "status.missing": ["Missing", "\u7F3A\u5931"],
  "status.too_old": ["Too old", "\u7248\u672C\u8FC7\u65E7"],
  "status.ok": ["OK", "\u6B63\u5E38"],
  "status.passed": ["Passed", "\u901A\u8FC7"],
  "status.not_validated": ["Not validated", "\u672A\u9A8C\u8BC1"],
  "status.limited_evidence": ["Limited evidence", "\u8BC1\u636E\u6709\u9650"],
  "status.review_required": ["Needs review", "\u5F85\u5BA1\u9605"],
  "status.trial": ["Trial", "\u8BD5\u7528"],
  "verdict.passed": ["Passed", "\u901A\u8FC7"],
  "verdict.failed": ["Failed \xB7 kept", "\u5931\u8D25\xB7\u4FDD\u7559"],
  "verdict.unknown": ["Unknown \xB7 not rerun", "\u672A\u77E5\xB7\u4E0D\u91CD\u8DD1"],
  "verdict.human": ["Needs a person", "\u5F85\u4EBA\u5DE5"],
  "verdict.open": ["Not checked", "\u672A\u68C0\u67E5"],
  "verdict.passed.tip": ["The independent recomputation passed. Test-mode evidence, not a release decision.", "\u72EC\u7ACB\u590D\u7B97\u901A\u8FC7\u3002\u6D4B\u8BD5\u6A21\u5F0F\u7684\u8BC1\u636E\uFF0C\u4E0D\u662F\u53D1\u5E03\u7ED3\u8BBA\u3002"],
  "verdict.failed.tip": ["The check failed. The attempt stays on record.", "\u590D\u7B97\u672A\u901A\u8FC7\uFF0C\u8FD9\u6B21\u5C1D\u8BD5\u4ECD\u4FDD\u7559\u5728\u8D26\u672C\u91CC\u3002"],
  "verdict.unknown.tip": ["The outcome was never confirmed. Kept on record, never rerun, never counted as success.", "\u7ED3\u679C\u59CB\u7EC8\u6CA1\u6709\u786E\u8BA4\u3002\u4FDD\u7559\u5728\u8D26\u672C\uFF0C\u4E0D\u91CD\u8DD1\uFF0C\u4E5F\u4E0D\u7B97\u6210\u529F\u3002"],
  "verdict.human.tip": ["Only a person can decide this, in a terminal.", "\u53EA\u6709\u4EBA\u80FD\u5728\u7EC8\u7AEF\u91CC\u505A\u8FD9\u4E2A\u51B3\u5B9A\u3002"],
  "verdict.open.tip": ["No check result recorded yet.", "\u8FD8\u6CA1\u6709\u590D\u7B97\u7ED3\u679C\u3002"],
  "overview.subtitle": ["Where this run stands.", "\u8FD9\u6B21\u8FD0\u884C\u8D70\u5230\u54EA\u4E86\u3002"],
  "overview.workflow": ["Run progress", "\u8FD0\u884C\u8FDB\u5EA6"],
  "overview.inferred": ["Stages are inferred from recorded facts. They are not an acceptance result, and an approval alone does not mean the change was applied.", "\u9636\u6BB5\u7531\u5DF2\u8BB0\u5F55\u7684\u4E8B\u5B9E\u63A8\u65AD\uFF0C\u4E0D\u662F\u9A8C\u6536\u7ED3\u8BBA\uFF1B\u6279\u51C6\u672C\u8EAB\u4E0D\u4EE3\u8868\u5DF2\u7ECF\u5E94\u7528\u3002"],
  "overview.pending": ["Waiting for you \xB7 {count}", "\u5F85\u4F60\u5BA1\u6279 \xB7 {count} \u9879"],
  "overview.pendingLine": ["Digest starts with this. Confirm in a terminal.", "\u6458\u8981\u4EE5\u6B64\u5F00\u5934\uFF0C\u5728\u7EC8\u7AEF\u786E\u8BA4\u3002"],
  "overview.openApprovals": ["Open approvals", "\u53BB\u5BA1\u6279"],
  "overview.deliveryUnknown": ["Approval recorded, no delivery data yet.", "\u5DF2\u8BB0\u5F55\u6279\u51C6\uFF0C\u8FD8\u6CA1\u6709\u4EA4\u4ED8\u6570\u636E\u3002"],
  "overview.currentAttempts": ["Attempts", "\u5C1D\u8BD5"],
  "overview.objects": ["Ledger counts", "\u8D26\u672C\u8BA1\u6570"],
  "overview.count.attempt": ["Attempts", "\u5C1D\u8BD5"],
  "overview.count.verification": ["Checks", "\u590D\u7B97"],
  "overview.count.approval": ["Approvals", "\u5BA1\u6279"],
  "overview.count.requirement": ["Requirements", "\u9700\u6C42"],
  "overview.lastCommit": ["Last commit", "\u6700\u65B0\u63D0\u4EA4"],
  "overview.allObjects": ["All types ({count})", "\u5168\u90E8\u7C7B\u578B\uFF08{count}\uFF09"],
  "overview.issues": ["{count} open issues", "{count} \u4E2A\u5F85\u5904\u7406\u95EE\u9898"],
  "overview.noIssues": ["No blockers", "\u6CA1\u6709\u963B\u585E"],
  "step.dispatch": ["Dispatch", "\u6D3E\u53D1"],
  "step.dispatchHint": ["Frozen packets", "\u51BB\u7ED3\u6267\u884C\u5305"],
  "step.attempt": ["Attempt", "\u5C1D\u8BD5"],
  "step.attemptHint": ["Strategies run", "\u5404\u7B56\u7565\u72EC\u7ACB\u8DD1"],
  "step.verify": ["Check", "\u590D\u7B97"],
  "step.verifyHint": ["Independent", "\u72EC\u7ACB\u590D\u6838"],
  "step.select": ["Select", "\u9009\u5B9A"],
  "step.selectHint": ["Reason kept", "\u7559\u4E0B\u7406\u7531"],
  "step.approval": ["Approval", "\u5BA1\u6279"],
  "step.approvalHint": ["A person decides", "\u4EBA\u6765\u51B3\u5B9A"],
  "step.delivery": ["Delivery", "\u4EA4\u4ED8"],
  "step.deliveryHint": ["Applied, observed", "\u89C2\u5BDF\u5230\u5DF2\u5E94\u7528"],
  "execution.subtitle": ["Strategies side by side. Failed and unknown ones stay.", "\u5404\u7B56\u7565\u5E76\u6392\uFF0C\u5931\u8D25\u548C\u672A\u77E5\u4E5F\u4FDD\u7559\u3002"],
  "execution.attempts": ["Attempts", "\u7B56\u7565\u5C1D\u8BD5"],
  "execution.runHint": ["To run a strategy, ask the assistant in the session to call pk_run_strategy.", "\u8981\u8DD1\u7B56\u7565\uFF0C\u8BF7\u8BA9\u4F1A\u8BDD\u91CC\u7684\u52A9\u624B\u8C03\u7528 pk_run_strategy\u3002"],
  "execution.noAttempts": ["No attempts yet. Ask the assistant to run a strategy.", "\u8FD8\u6CA1\u6709\u5C1D\u8BD5\uFF0C\u8BA9\u52A9\u624B\u8DD1\u4E00\u4E2A\u7B56\u7565\u3002"],
  "execution.incomparable": ["Not comparable", "\u4E0D\u53EF\u6BD4"],
  "execution.selection": ["Selected {strategy}", "\u9009\u5B9A {strategy}"],
  "execution.basis": ["Basis", "\u4F9D\u636E"],
  "execution.retained": ["{count} failed or unknown kept on record", "{count} \u4E2A\u5931\u8D25\u6216\u672A\u77E5\u5C1D\u8BD5\u5DF2\u4FDD\u7559"],
  "execution.unknownNote": ["Unconfirmed outcomes are not success and are never rerun.", "\u672A\u786E\u8BA4\u7684\u7ED3\u679C\u4E0D\u7B97\u6210\u529F\uFF0C\u4E5F\u4E0D\u4F1A\u91CD\u8DD1\u3002"],
  "execution.fit": ["alpha", "\u03B1"],
  "execution.exit": ["Exit", "\u9000\u51FA\u7801"],
  "execution.cost": ["Cost", "\u6210\u672C"],
  "execution.costUnknown": ["Not reported", "\u672A\u4E0A\u62A5"],
  "execution.costTip": ["Unreported cost is unknown, not zero.", "\u672A\u4E0A\u62A5\u7684\u6210\u672C\u662F\u672A\u77E5\uFF0C\u4E0D\u7B49\u4E8E\u96F6\u3002"],
  "execution.revisionsShort": ["{count} rev", "{count} \u7248"],
  "execution.operation": ["Delivery operation", "\u4EA4\u4ED8\u64CD\u4F5C"],
  "execution.operationFold": ["Look up an existing one", "\u67E5\u8BE2\u5DF2\u6709\u64CD\u4F5C"],
  "execution.operationId": ["Operation ID", "\u64CD\u4F5C ID"],
  "execution.operationKind": ["Kind", "\u7C7B\u578B"],
  "execution.operationPlaceholder": ["Operation ID", "\u64CD\u4F5C ID"],
  "execution.operationPrompt": ["Enter an operation ID to see its state.", "\u8F93\u5165\u64CD\u4F5C ID \u67E5\u770B\u72B6\u6001\u3002"],
  "execution.operationState": ["Operation states", "\u64CD\u4F5C\u72B6\u6001"],
  "permissions.subtitle": ["Requests waiting on a person.", "\u7B49\u4EBA\u6765\u51B3\u5B9A\u7684\u7533\u8BF7\u3002"],
  "permissions.queue": ["Approval queue", "\u5BA1\u6279\u961F\u5217"],
  "permissions.noPending": ["Nothing waiting.", "\u6CA1\u6709\u5F85\u5BA1\u6279\u7684\u7533\u8BF7\u3002"],
  "permissions.pendingDrawer": ["Waiting for you \xB7 {count}", "\u5F85\u4F60\u5BA1\u6279 \xB7 {count} \u9879"],
  "permissions.digest": ["Digest starts with", "\u6458\u8981\u524D 8 \u4F4D"],
  "permissions.bindTip": ["The approval binds this exact snapshot. If the candidate changes, the approval is voided.", "\u5BA1\u6279\u7ED1\u5B9A\u8FD9\u4EFD\u5FEB\u7167\uFF1B\u5019\u9009\u4E00\u53D8\uFF0C\u5BA1\u6279\u5373\u4F5C\u5E9F\u3002"],
  "permissions.terminal": ["Run tools\\pk-human-approve.ps1 in a terminal and type the first 8 digest characters to confirm.", "\u5728\u7EC8\u7AEF\u8FD0\u884C tools\\pk-human-approve.ps1\uFF0C\u8F93\u5165\u6458\u8981\u524D 8 \u4F4D\u786E\u8BA4"],
  "permissions.snapshot": ["Snapshot", "\u5FEB\u7167"],
  "permissions.headVersion": ["Head version", "\u5934\u7248\u672C"],
  "permissions.expires": ["Expires", "\u5230\u671F"],
  "permissions.commit": ["Commit", "\u63D0\u4EA4"],
  "permissions.candidate": ["Candidate", "\u5019\u9009"],
  "permissions.countdown": ["Left", "\u5269\u4F59"],
  "permissions.remaining": ["{minutes}:{seconds}", "{minutes}:{seconds}"],
  "permissions.expiredTime": ["Expired", "\u5DF2\u5230\u671F"],
  "permissions.morePending": ["{count} more in Approvals", "\u53E6\u6709 {count} \u9879\u5728\u5BA1\u6279\u9875"],
  "permissions.humanTip": ["This panel only shows the queue. The machine channel cannot decide. AGH tool pop-ups and kernel approvals are two separate layers.", "\u672C\u9762\u677F\u53EA\u5C55\u793A\u961F\u5217\uFF0C\u673A\u5668\u901A\u9053\u4E0D\u80FD\u51B3\u5B9A\u3002AGH \u7684\u5DE5\u5177\u5F39\u7A97\u4E0E\u5185\u6838\u5BA1\u6279\u662F\u4E24\u5C42\u3002"],
  "permissions.historical": ["History view: no live countdown.", "\u5386\u53F2\u89C6\u56FE\uFF1A\u4E0D\u663E\u793A\u5012\u8BA1\u65F6\u3002"],
  "events.subtitle": ["What the ledger recorded, newest first.", "\u8D26\u672C\u8BB0\u4E0B\u7684\u4E8B\u4EF6\uFF0C\u65B0\u7684\u5728\u524D\u3002"],
  "events.stream": ["Event ledger", "\u4E8B\u4EF6\u8D26\u672C"],
  "events.hint": ["Reads up to 100 events after a cursor. Read more continues after the newest shown.", "\u6BCF\u6B21\u8BFB\u53D6\u6E38\u6807\u4E4B\u540E\u6700\u591A 100 \u6761\uFF1B\u7EE7\u7EED\u8BFB\u53D6\u4F1A\u63A5\u7740\u6700\u65B0\u4E00\u6761\u5F80\u540E\u3002"],
  "events.search": ["Search type, command, object, #", "\u641C\u7D22\u7C7B\u578B\u3001\u547D\u4EE4\u3001\u5BF9\u8C61\u3001\u63D0\u4EA4\u53F7"],
  "events.filterByType": ["Type", "\u7C7B\u578B"],
  "events.noEvents": ["No events after this cursor.", "\u8FD9\u4E2A\u6E38\u6807\u4E4B\u540E\u6CA1\u6709\u4E8B\u4EF6\u3002"],
  "events.noMatch": ["No event matches.", "\u6CA1\u6709\u5339\u914D\u7684\u4E8B\u4EF6\u3002"],
  "events.more": ["Read more", "\u7EE7\u7EED\u8BFB\u53D6"],
  "events.fromStart": ["From start", "\u4ECE\u5934\u5F00\u59CB"],
  "events.command": ["Command", "\u547D\u4EE4"],
  "events.entries": ["{count} events", "{count} \u6761"],
  "structure.subtitle": ["Pick a module to light up its neighbours.", "\u9009\u4E00\u4E2A\u6A21\u5757\uFF0C\u70B9\u4EAE\u5B83\u7684\u90BB\u5C45\u3002"],
  "structure.modules": ["Module tree", "\u6A21\u5757\u6811"],
  "structure.docHint": ["Read from the module registry on disk, also in history view.", "\u8BFB\u81EA\u78C1\u76D8\u4E0A\u7684\u6A21\u5757\u767B\u8BB0\u8868\uFF0C\u5386\u53F2\u89C6\u56FE\u4E0B\u4E5F\u4E00\u6837\u3002"],
  "structure.navigation": ["Module hierarchy", "\u6A21\u5757\u5C42\u7EA7"],
  "structure.graph": ["Neighbours of the selected module", "\u9009\u4E2D\u6A21\u5757\u7684\u90BB\u5C45"],
  "structure.dependency": ["depends on", "\u4F9D\u8D56"],
  "structure.related": ["related to", "\u76F8\u5173"],
  "structure.inLabel": ["{n} in", "{n} \u5165"],
  "structure.outLabel": ["{n} out", "{n} \u51FA"],
  "structure.degreeIncoming": ["Modules that depend on this one", "\u4F9D\u8D56\u672C\u6A21\u5757\u7684\u6A21\u5757\u6570"],
  "structure.degreeOutgoing": ["Modules this one depends on", "\u672C\u6A21\u5757\u4F9D\u8D56\u7684\u6A21\u5757\u6570"],
  "structure.degreeHint": ["Counted from declared dependencies, not runtime coupling.", "\u6309\u58F0\u660E\u7684\u4F9D\u8D56\u7EDF\u8BA1\uFF0C\u4E0D\u662F\u8FD0\u884C\u8026\u5408\u3002"],
  "structure.couplingDegree": ["Coupling", "\u8026\u5408"],
  "structure.neighbours": ["{count} neighbours", "{count} \u4E2A\u90BB\u5C45"],
  "structure.businessGraph": ["Run objects", "\u8FD0\u884C\u5BF9\u8C61"],
  "structure.runtimeHint": ["Object references from the kernel, separate from the module tree.", "\u5185\u6838\u91CC\u7684\u5BF9\u8C61\u5F15\u7528\uFF0C\u4E0E\u6A21\u5757\u6811\u4E92\u76F8\u72EC\u7ACB\u3002"],
  "structure.expand": ["Expand {id}", "\u5C55\u5F00 {id}"],
  "structure.collapse": ["Collapse {id}", "\u6298\u53E0 {id}"],
  "structure.cycle": ["Cycle", "\u6210\u73AF"],
  "structure.status": ["Status", "\u72B6\u6001"],
  "structure.updated": ["Updated", "\u66F4\u65B0"],
  "structure.revision": ["Revision", "\u4FEE\u8BA2"],
  "structure.requirements": ["Requirements", "\u9700\u6C42"],
  "structure.linkedRecords": ["Linked records", "\u5173\u8054\u8BB0\u5F55"],
  "structure.relations": ["Relations", "\u5173\u7CFB"],
  "structure.tone.implemented": ["Declared implemented", "\u58F0\u660E\u5DF2\u5B9E\u73B0"],
  "structure.tone.limited": ["Implemented, with limits", "\u5DF2\u5B9E\u73B0\uFF0C\u6709\u9650\u5236"],
  "structure.tone.unknown": ["Not stated", "\u672A\u58F0\u660E"],
  "structure.openReq": ["Open {id}", "\u6253\u5F00 {id}"],
  "structure.conversations": ["Conversations", "\u5BF9\u8BDD"],
  "structure.noConversation": ["No conversation mapping recorded.", "\u672A\u8BB0\u5F55\u5BF9\u8BDD\u6620\u5C04\u3002"],
  "structure.noConversationTip": ["conversation_refs is empty for this module. Linked records come from its own document.", "\u8FD9\u4E2A\u6A21\u5757\u7684 conversation_refs \u4E3A\u7A7A\uFF1B\u5173\u8054\u8BB0\u5F55\u6765\u81EA\u5B83\u81EA\u5DF1\u7684\u6587\u6863\u3002"],
  "structure.linkedList": ["Linked records", "\u5173\u8054\u8BB0\u5F55"],
  "trace.queryTitle": ["Trace another root", "\u8FFD\u6EAF\u5176\u4ED6\u6839"],
  "trace.queryHint": ["Leave all four blank for the session task, or fill all four.", "\u56DB\u9879\u5168\u7A7A\u7528\u4F1A\u8BDD\u4EFB\u52A1\uFF0C\u5426\u5219\u56DB\u9879\u90FD\u8981\u586B\u3002"],
  "trace.fullRootRequired": ["Fill all four fields or none.", "\u56DB\u9879\u90FD\u8981\u586B\uFF0C\u6216\u5168\u90E8\u7559\u7A7A\u3002"],
  "trace.project_id": ["Project ID", "\u9879\u76EE ID"],
  "trace.object_type": ["Object type", "\u5BF9\u8C61\u7C7B\u578B"],
  "trace.object_id": ["Object ID", "\u5BF9\u8C61 ID"],
  "trace.revision_id": ["Revision ID", "\u4FEE\u8BA2 ID"],
  "trace.direction": ["Direction", "\u65B9\u5411"],
  "trace.depth": ["Depth", "\u6DF1\u5EA6"],
  "trace.both": ["Both", "\u53CC\u5411"],
  "trace.incoming": ["Incoming", "\u5165\u8FB9"],
  "trace.outgoing": ["Outgoing", "\u51FA\u8FB9"],
  "trace.truncated": ["Cut off at the depth limit.", "\u5DF2\u5728\u6DF1\u5EA6\u4E0A\u9650\u5904\u622A\u65AD\u3002"],
  "trace.root": ["Root", "\u6839"],
  "trace.nodeCount": ["Nodes", "\u8282\u70B9"],
  "trace.edgeCount": ["Edges", "\u8FB9"],
  "trace.graphLabel": ["Run object graph", "\u8FD0\u884C\u5BF9\u8C61\u56FE"],
  "trace.records": ["Records", "\u8BB0\u5F55"],
  "trace.relation": ["Relation", "\u5173\u7CFB"],
  "trace.exists": ["Exists", "\u5B58\u5728"],
  "requirements.subtitle": ["Which requirements reached a packet.", "\u54EA\u4E9B\u9700\u6C42\u843D\u5230\u4E86\u6267\u884C\u5305\u3002"],
  "requirements.coverage": ["Coverage", "\u8986\u76D6"],
  "requirements.scope": ["The demo starts at dispatch_ready, so this shows handoff results. Requirement entry is a separate tool flow.", "\u6F14\u793A\u4ECE dispatch_ready \u5F00\u59CB\uFF0C\u8FD9\u91CC\u53EA\u770B\u4EA4\u63A5\u7ED3\u679C\uFF1B\u9700\u6C42\u5F55\u5165\u8D70\u72EC\u7ACB\u5DE5\u5177\u6D41\u7A0B\u3002"],
  "requirements.denominator": ["Applicable", "\u9002\u7528"],
  "requirements.covered": ["Covered", "\u5DF2\u8986\u76D6"],
  "requirements.notApplicable": ["Not applicable", "\u4E0D\u9002\u7528"],
  "requirements.ratio": ["{covered} / {total} linked", "\u5DF2\u94FE\u63A5 {covered} / {total}"],
  "requirements.noDenominator": ["No ratio without applicable requirements.", "\u6CA1\u6709\u9002\u7528\u9700\u6C42\uFF0C\u4E0D\u8BA1\u7B97\u6BD4\u4F8B\u3002"],
  "requirements.denominatorHint": ["Applicable requirements with zero links stay in the total.", "\u96F6\u94FE\u63A5\u7684\u9002\u7528\u9700\u6C42\u4ECD\u8BA1\u5165\u603B\u6570\u3002"],
  "requirements.requirement": ["Requirement", "\u9700\u6C42"],
  "requirements.links": ["Links", "\u94FE\u63A5"],
  "requirements.packets": ["Packets", "\u6267\u884C\u5305"],
  "requirements.coverageStatus": ["Coverage", "\u8986\u76D6"],
  "requirements.reason": ["Reason", "\u7406\u7531"],
  "requirements.noRequirements": ["No requirements at this watermark.", "\u8FD9\u4E2A\u6C34\u4F4D\u6CA1\u6709\u9700\u6C42\u3002"],
  "requirements.handoffTrace": ["Handoff trace", "\u4EA4\u63A5\u8FFD\u6EAF"],
  "requirements.chain": ["Requirement \u2192 design \u2192 packet \u2192 attempt.", "\u9700\u6C42 \u2192 \u65B9\u6848 \u2192 \u6267\u884C\u5305 \u2192 \u5C1D\u8BD5\u3002"],
  "errors.subtitle": ["Failures and unknowns, counted from what is loaded.", "\u6309\u5DF2\u52A0\u8F7D\u6570\u636E\u7EDF\u8BA1\u7684\u5931\u8D25\u4E0E\u672A\u77E5\u3002"],
  "errors.attemptStates": ["Attempt states", "\u5C1D\u8BD5\u72B6\u6001"],
  "errors.eventTypes": ["Timeline types", "\u65F6\u95F4\u7EBF\u7C7B\u578B"],
  "errors.retained": ["Kept on record", "\u5DF2\u4FDD\u7559"],
  "errors.retainedCount": ["Kept", "\u4FDD\u7559"],
  "errors.blockerCount": ["Blockers", "\u963B\u585E"],
  "errors.blockers": ["Blockers", "\u963B\u585E\u9879"],
  "errors.derivedNote": ["Counted in this panel from the loaded page, not a kernel statistic.", "\u7531\u672C\u9762\u677F\u6309\u5DF2\u52A0\u8F7D\u7684\u9875\u7EDF\u8BA1\uFF0C\u4E0D\u662F\u5185\u6838\u7EDF\u8BA1\u3002"],
  "errors.noObservations": ["Nothing to count yet.", "\u6682\u65E0\u53EF\u7EDF\u8BA1\u7684\u6570\u636E\u3002"],
  "errors.series": ["Failed and unknown by commit", "\u5931\u8D25\u4E0E\u672A\u77E5\uFF08\u6309\u63D0\u4EA4\uFF09"],
  "errors.sequence": ["Commit", "\u63D0\u4EA4"],
  "errors.noExplicitEvents": ["No failed or unknown event names on this page.", "\u8FD9\u4E00\u9875\u6CA1\u6709\u540D\u79F0\u6807\u660E\u5931\u8D25\u6216\u672A\u77E5\u7684\u4E8B\u4EF6\u3002"],
  "errors.seriesTip": ["Only event names that say failed, failure or unknown are counted.", "\u53EA\u7EDF\u8BA1\u540D\u79F0\u542B failed\u3001failure \u6216 unknown \u7684\u4E8B\u4EF6\u3002"],
  "skills.subtitle": ["Registered skills, plus an assessment preview.", "\u5DF2\u767B\u8BB0\u7684 Skill\uFF0C\u4EE5\u53CA\u8BC4\u4F30\u9884\u89C8\u3002"],
  "skills.registry": ["Skill registry", "Skill \u767B\u8BB0"],
  "skills.registryHint": ["Versions and scope are declared in a document, not runtime evidence. History watermarks do not change it.", "\u7248\u672C\u4E0E\u8303\u56F4\u662F\u6587\u6863\u58F0\u660E\uFF0C\u4E0D\u662F\u8FD0\u884C\u8BC1\u636E\uFF1B\u5386\u53F2\u6C34\u4F4D\u4E0D\u5F71\u54CD\u5B83\u3002"],
  "skills.currentVersion": ["Current", "\u5F53\u524D"],
  "skills.version": ["Version", "\u7248\u672C"],
  "skills.scope": ["Scope", "\u9002\u7528\u8303\u56F4"],
  "skills.sourceRevision": ["Revision", "\u4FEE\u8BA2"],
  "skills.applies_to": ["Applies to", "\u9002\u7528\u4E8E"],
  "skills.prerequisites": ["Needs", "\u524D\u63D0"],
  "skills.exclusions": ["Not for", "\u4E0D\u9002\u7528\u4E8E"],
  "skills.reviewRefs": ["Reviews", "\u5BA1\u9605"],
  "skills.evidenceRefs": ["Evidence", "\u8BC1\u636E"],
  "skills.recordedScores": ["Scores", "\u8BC4\u5206"],
  "skills.unassessed": ["Not assessed", "\u672A\u8BC4\u4F30"],
  "skills.noRecordedScores": ["The registry holds no scores.", "\u767B\u8BB0\u8868\u91CC\u6CA1\u6709\u5206\u503C\u3002"],
  "skills.formPreview": ["Assessment form", "\u8BC4\u4F30\u8868\u5355"],
  "skills.scoreHint": ["Each dimension takes 0, 1, 2 or empty. No total, no average, no rating of a person.", "\u6BCF\u4E2A\u7EF4\u5EA6\u586B 0\u30011\u30012 \u6216\u7559\u7A7A\uFF1B\u4E0D\u7B97\u603B\u5206\u548C\u5E73\u5747\u5206\uFF0C\u4E5F\u4E0D\u8BC4\u4EF7\u4EBA\u3002"],
  "skills.newSkill": ["Skill ID", "Skill ID"],
  "skills.namePlaceholder": ["example.skill", "example.skill"],
  "skills.scopePlaceholder": ["Where it applies", "\u9002\u7528\u573A\u666F"],
  "skills.localOnly": ["Nothing here is saved.", "\u8FD9\u91CC\u586B\u7684\u5185\u5BB9\u4E0D\u4F1A\u4FDD\u5B58\u3002"],
  "score.correctness": ["Correctness", "\u6B63\u786E\u6027"],
  "score.applicability": ["Applicability", "\u9002\u7528\u6027"],
  "score.reuse_benefit": ["Reuse benefit", "\u590D\u7528\u6536\u76CA"],
  "score.maintainability": ["Maintainability", "\u53EF\u7EF4\u62A4\u6027"],
  "score.value0": ["0", "0"],
  "score.value1": ["1", "1"],
  "score.value2": ["2", "2"],
  "environment.subtitle": ["Recorded checks of the toolchain.", "\u5DF2\u8BB0\u5F55\u7684\u5DE5\u5177\u94FE\u68C0\u67E5\u3002"],
  "environment.report": ["Environment report", "\u73AF\u5883\u62A5\u544A"],
  "environment.noProbe": ["No environment check recorded yet.", "\u8FD8\u6CA1\u6709\u73AF\u5883\u68C0\u67E5\u8BB0\u5F55\u3002"],
  "environment.sourceFailed": ["The environment source failed. That is not the same as no check.", "\u73AF\u5883\u6570\u636E\u6765\u6E90\u5931\u8D25\uFF0C\u4E0D\u7B49\u4E8E\u6CA1\u68C0\u67E5\u8FC7\u3002"],
  "environment.readOnlyHint": ["Checks run as session tools. This panel only shows their results.", "\u68C0\u67E5\u7531\u4F1A\u8BDD\u5DE5\u5177\u6267\u884C\uFF0C\u8FD9\u91CC\u53EA\u5C55\u793A\u7ED3\u679C\u3002"],
  "environment.checkedAt": ["Checked", "\u68C0\u67E5\u65F6\u95F4"],
  "environment.freshness": ["Freshness", "\u65B0\u9C9C\u5EA6"],
  "environment.snapshot": ["Snapshot", "\u5FEB\u7167"],
  "environment.dataState": ["Data", "\u6570\u636E"],
  "environment.requirement": ["Requirement", "\u8981\u6C42"],
  "environment.requiredVersion": ["Needs", "\u8981\u6C42\u7248\u672C"],
  "environment.installedVersion": ["Found", "\u5DF2\u88C5\u7248\u672C"],
  "environment.path": ["Path", "\u8DEF\u5F84"],
  "environment.bucketEmpty": ["Nothing here.", "\u8FD9\u4E00\u7C7B\u6CA1\u6709\u6761\u76EE\u3002"],
  "versions.subtitle": ["Revisions, heads and events over time.", "\u968F\u65F6\u95F4\u53D8\u5316\u7684\u4FEE\u8BA2\u3001\u5934\u7248\u672C\u548C\u4E8B\u4EF6\u3002"],
  "versions.watermark": ["Look back", "\u56DE\u770B"],
  "versions.watermarkHint": ["Applies the watermark to run views. Document views stay current.", "\u628A\u6C34\u4F4D\u5E94\u7528\u5230\u8FD0\u884C\u6570\u636E\u89C6\u56FE\uFF1B\u6587\u6863\u89C6\u56FE\u59CB\u7EC8\u662F\u5F53\u524D\u7684\u3002"],
  "versions.viewHistory": ["View this commit", "\u56DE\u770B\u6B64\u63D0\u4EA4"],
  "versions.returnCurrent": ["Back to now", "\u56DE\u5230\u5F53\u524D"],
  "versions.noHead": ["No usable head yet.", "\u6682\u65E0\u53EF\u7528\u7684\u6700\u65B0\u6C34\u4F4D\u3002"],
  "versions.timeline": ["Timeline", "\u65F6\u95F4\u7EBF"],
  "versions.objectFilter": ["Object type", "\u5BF9\u8C61\u7C7B\u578B"],
  "versions.firstPage": ["First page", "\u7B2C\u4E00\u9875"],
  "versions.nextPage": ["Next page", "\u4E0B\u4E00\u9875"],
  "versions.pageCount": ["{count} on this page", "\u672C\u9875 {count} \u6761"],
  "versions.filterScope": ["Filters apply to the loaded page only. Entries are grouped by kind across pages, so order is not global.", "\u8FC7\u6EE4\u53EA\u4F5C\u7528\u4E8E\u5DF2\u52A0\u8F7D\u7684\u9875\uFF1B\u8DE8\u9875\u6309\u7C7B\u522B\u5206\u6BB5\uFF0C\u4E0D\u662F\u5168\u5C40\u987A\u5E8F\u3002"],
  "versions.noEvents": ["Nothing at this watermark.", "\u8FD9\u4E2A\u6C34\u4F4D\u6CA1\u6709\u6761\u76EE\u3002"],
  "versions.noMatchingEvents": ["No match on this page.", "\u8FD9\u4E00\u9875\u6CA1\u6709\u5339\u914D\u9879\u3002"],
  "versions.eventType": ["Event", "\u4E8B\u4EF6"],
  "versions.kind.revision": ["Revision", "\u4FEE\u8BA2"],
  "versions.kind.head": ["Head", "\u5934\u7248\u672C"],
  "versions.kind.event": ["Event", "\u4E8B\u4EF6"],
  "versions.rulesHint": ["Saving and publishing rules is outside this read-only panel.", "\u89C4\u5219\u7684\u4FDD\u5B58\u4E0E\u53D1\u5E03\u4E0D\u5728\u8FD9\u4E2A\u53EA\u8BFB\u9762\u677F\u5185\u3002"],
  "workspace.subtitle": ["Several projects in one place.", "\u591A\u4E2A\u9879\u76EE\u653E\u5728\u4E00\u5904\u3002"],
  "workspace.previewNote": ["Example data and local state. The kernel commands below do not exist yet.", "\u793A\u4F8B\u6570\u636E\u4E0E\u672C\u5730\u72B6\u6001\uFF1B\u4E0B\u5217\u5185\u6838\u547D\u4EE4\u5C1A\u672A\u5B9E\u73B0\u3002"],
  "workspace.current": ["Current", "\u5F53\u524D"],
  "workspace.path": ["Path", "\u8DEF\u5F84"],
  "workspace.projectCount": ["Projects", "\u9879\u76EE\u6570"],
  "workspace.currentProject": ["Active project", "\u6D3B\u52A8\u9879\u76EE"],
  "workspace.projectId": ["Project ID", "\u9879\u76EE ID"],
  "workspace.hasStore": ["Has project.sqlite", "\u6709 project.sqlite"],
  "workspace.lastOpened": ["Last opened", "\u6700\u540E\u6253\u5F00"],
  "workspace.allWorkspaces": ["Workspaces", "\u5DE5\u4F5C\u533A"],
  "workspace.projects": ["projects", "\u4E2A\u9879\u76EE"],
  "workspace.switchTo": ["Switch", "\u5207\u6362"],
  "workspace.create": ["New workspace", "\u65B0\u5EFA\u5DE5\u4F5C\u533A"],
  "workspace.allProjects": ["Projects", "\u9879\u76EE"],
  "workspace.workspace": ["Workspace", "\u6240\u5C5E\u5DE5\u4F5C\u533A"],
  "workspace.open": ["Open", "\u6253\u5F00"],
  "workspace.import": ["Import", "\u5BFC\u5165"],
  "workspace.importProject": ["Import a project", "\u5BFC\u5165\u9879\u76EE"],
  "workspace.importSource": ["Source (path, Git URL or sqlite)", "\u6765\u6E90\uFF08\u8DEF\u5F84\u3001Git \u5730\u5740\u6216 sqlite\uFF09"],
  "workspace.sourcePlaceholder": ["D:\\path\\to\\project", "D:\\path\\to\\project"],
  "workspace.importName": ["Name", "\u540D\u79F0"],
  "workspace.namePlaceholder": ["my-project", "my-project"],
  "workspace.importAction": ["Import", "\u5BFC\u5165"],
  "workspace.implementation": ["Missing kernel commands", "\u7F3A\u5C11\u7684\u5185\u6838\u547D\u4EE4"],
  "workspace.cmdList": ["list workspaces", "\u5217\u51FA\u5DE5\u4F5C\u533A"],
  "workspace.cmdCreate": ["create a workspace", "\u65B0\u5EFA\u5DE5\u4F5C\u533A"],
  "workspace.cmdImport": ["import a project", "\u5BFC\u5165\u9879\u76EE"],
  "workspace.cmdSelect": ["switch project", "\u5207\u6362\u9879\u76EE"],
  "workspace.implementationNote": ["Design: docs/frontend/workspace-project-design.md", "\u8BBE\u8BA1\uFF1Adocs/frontend/workspace-project-design.md"],
  "knowledge.subtitle": ["Example data. Not connected yet.", "\u793A\u4F8B\u6570\u636E\uFF0C\u5C1A\u672A\u63A5\u5165\u3002"],
  "knowledge.notConnected": ["The knowledge module has no core RPC yet. The user profile is a Markdown document.", "\u77E5\u8BC6\u6A21\u5757\u8FD8\u6CA1\u6709\u6838\u5FC3 RPC\uFF1B\u7528\u6237\u753B\u50CF\u662F\u4E00\u4EFD Markdown \u6587\u6863\u3002"],
  "knowledge.tree": ["Knowledge tree", "\u77E5\u8BC6\u6811"],
  "knowledge.project": ["Project context", "\u9879\u76EE\u4E0A\u4E0B\u6587"],
  "knowledge.contracts": ["Contracts and boundaries", "\u5951\u7EA6\u4E0E\u8FB9\u754C"],
  "knowledge.decisions": ["Design decisions", "\u8BBE\u8BA1\u51B3\u5B9A"],
  "knowledge.evidence": ["Evidence references", "\u8BC1\u636E\u5F15\u7528"],
  "knowledge.profile": ["Learning profile", "\u5B66\u4E60\u753B\u50CF"],
  "knowledge.preferences": ["Writing preferences", "\u8868\u8FBE\u504F\u597D"],
  "knowledge.feedback": ["Feedback by context", "\u5206\u573A\u666F\u53CD\u9988"],
  "knowledge.budget": ["Context budget", "\u4E0A\u4E0B\u6587\u9884\u7B97"],
  "knowledge.budgetHint": ["Example trade-offs, no measured token totals.", "\u793A\u4F8B\u53D6\u820D\uFF0C\u6CA1\u6709\u5B9E\u6D4B token \u6570\u3002"],
  "knowledge.mandatory": ["Must keep", "\u5FC5\u987B\u4FDD\u7559"],
  "knowledge.mandatoryDetail": ["Task boundary, exact inputs, source references.", "\u4EFB\u52A1\u8FB9\u754C\u3001\u7CBE\u786E\u8F93\u5165\u3001\u6765\u6E90\u5F15\u7528\u3002"],
  "knowledge.retained": ["Kept", "\u4FDD\u7559"],
  "knowledge.optional": ["Optional background", "\u53EF\u9009\u80CC\u666F"],
  "knowledge.optionalDetail": ["Dropped first when the budget is tight.", "\u9884\u7B97\u7D27\u5F20\u65F6\u6700\u5148\u820D\u5F03\u3002"],
  "knowledge.optionalIncluded": ["Included in this example.", "\u672C\u793A\u4F8B\u5305\u542B\u3002"],
  "knowledge.optionalExcluded": ["Left out of this example.", "\u672C\u793A\u4F8B\u7701\u7565\u3002"],
  "knowledge.provenance": ["Source and summary", "\u6765\u6E90\u4E0E\u6458\u8981"],
  "knowledge.sourceLimit": ["A connected excerpt keeps its exact source version and location.", "\u63A5\u5165\u540E\u6458\u5F55\u4F1A\u4FDD\u7559\u7CBE\u786E\u7684\u6765\u6E90\u7248\u672C\u4E0E\u4F4D\u7F6E\u3002"],
  "knowledge.sampleSummary": ["Example summary: prefer direct, traceable explanations.", "\u793A\u4F8B\u6458\u8981\uFF1A\u4F18\u5148\u7ED9\u51FA\u76F4\u63A5\u3001\u53EF\u8FFD\u6EAF\u7684\u8BF4\u660E\u3002"],
  "knowledge.descriptive": ["Describes context and preferences. Never scores a person.", "\u53EA\u63CF\u8FF0\u4E0A\u4E0B\u6587\u4E0E\u504F\u597D\uFF0C\u4E0D\u7ED9\u4EBA\u6253\u5206\u3002"],
  "documents.subtitle": ["Project documents on disk.", "\u78C1\u76D8\u4E0A\u7684\u9879\u76EE\u6587\u6863\u3002"],
  "documents.index": ["Index ({count})", "\u76EE\u5F55\uFF08{count}\uFF09"],
  "documents.search": ["Filter by path or title", "\u6309\u8DEF\u5F84\u6216\u6807\u9898\u8FC7\u6EE4"],
  "documents.reader": ["Reader", "\u9605\u8BFB"],
  "documents.selectPrompt": ["Pick a document on the left.", "\u5728\u5DE6\u8FB9\u9009\u4E00\u4EFD\u6587\u6863\u3002"],
  "documents.bytes": ["{bytes} bytes", "{bytes} \u5B57\u8282"],
  "documents.references": ["{total} references, {missing} missing", "\u5F15\u7528 {total} \u4E2A\uFF0C\u7F3A\u5931 {missing} \u4E2A"],
  "documents.exists": ["found", "\u5B58\u5728"],
  "documents.missing": ["missing", "\u7F3A\u5931"],
  "documents.planNotice": ["Working draft. Items about pk_plan and the planning service are void: planning belongs to AGH and the model. Unchecked items are not done.", "\u5DE5\u4F5C\u8349\u7A3F\uFF1Apk_plan \u4E0E\u89C4\u5212\u670D\u52A1\u76F8\u5173\u6761\u76EE\u5DF2\u4F5C\u5E9F\uFF0C\u89C4\u5212\u5F52 AGH \u4E0E\u6A21\u578B\u3002\u672A\u52FE\u9009\u7684\u6761\u76EE\u5C1A\u672A\u5B8C\u6210\u3002"],
  "documents.category.plans": ["Plans", "\u8BA1\u5212"],
  "documents.category.handoffs": ["Handoffs", "\u4EA4\u63A5"],
  "documents.category.requirements": ["Requirements", "\u9700\u6C42"],
  "documents.category.architecture": ["Architecture", "\u67B6\u6784"],
  "documents.category.modules": ["Modules", "\u6A21\u5757"],
  "documents.category.frontend": ["Frontend", "\u524D\u7AEF"],
  "documents.category.records": ["Records", "\u8BB0\u5F55"],
  "documents.category.acceptance": ["Acceptance", "\u9A8C\u6536"],
  "documents.category.reviews": ["Reviews", "\u8BC4\u5BA1"],
  "design.subtitle": ["Pain point, mechanism, code, status.", "\u75DB\u70B9\u3001\u673A\u5236\u3001\u4EE3\u7801\u3001\u72B6\u6001\u3002"],
  "design.map": ["Capability map", "\u80FD\u529B\u5730\u56FE"],
  "design.mapTip": ["Each row names the code or test that backs it. Status is taken from the project documents and tests, not measured here. Design previews are not implemented.", "\u6BCF\u884C\u90FD\u6807\u51FA\u5BF9\u5E94\u7684\u4EE3\u7801\u6216\u6D4B\u8BD5\u3002\u72B6\u6001\u53D6\u81EA\u9879\u76EE\u6587\u6863\u4E0E\u6D4B\u8BD5\uFF0C\u8FD9\u91CC\u4E0D\u505A\u6D4B\u91CF\uFF1B\u8BBE\u8BA1\u9884\u89C8\u5C1A\u672A\u5B9E\u73B0\u3002"],
  "design.col.item": ["Pain point", "\u75DB\u70B9"],
  "design.col.how": ["Mechanism", "\u673A\u5236"],
  "design.col.path": ["Code and tests", "\u4EE3\u7801\u4E0E\u6D4B\u8BD5"],
  "design.col.status": ["Status", "\u72B6\u6001"],
  "design.all": ["All", "\u5168\u90E8"],
  "design.status.tested": ["Built and tested", "\u5DF2\u5B9E\u73B0\u5E76\u6D4B\u8BD5"],
  "design.status.unwired": ["Built, not wired", "\u5DF2\u5B9E\u73B0\u672A\u63A5\u901A"],
  "design.status.preview": ["Design preview", "\u8BBE\u8BA1\u9884\u89C8"],
  "design.note.document": ["Document declaration", "\u6587\u6863\u58F0\u660E"],
  "design.pillar.memory": ["Memory and record", "\u8BB0\u5FC6\u4E0E\u8BB0\u5F55"],
  "design.pillar.trust": ["Trust and governance", "\u4FE1\u4EFB\u4E0E\u6CBB\u7406"],
  "design.pillar.view": ["Structure and visibility", "\u7ED3\u6784\u4E0E\u53EF\u89C6"],
  "design.pillar.integration": ["Integration", "\u96C6\u6210"],
  "design.ledger.name": ["Immutable fact ledger", "\u4E0D\u53EF\u53D8\u4E8B\u5B9E\u8D26\u672C"],
  "design.ledger.pain": ["What happened is hard to prove, and records can be edited.", "\u4E8B\u540E\u8BF4\u4E0D\u6E05\u53D1\u751F\u8FC7\u4EC0\u4E48\uFF0C\u8BB0\u5F55\u8FD8\u53EF\u80FD\u88AB\u6539\u3002"],
  "design.ledger.how": ["Append-only revisions. Reads freeze at a watermark. Survives restart.", "\u53EA\u8FFD\u52A0\u7684\u4FEE\u8BA2\uFF1B\u8BFB\u53D6\u51BB\u7ED3\u5728\u6C34\u4F4D\u4E0A\uFF1B\u91CD\u542F\u540E\u4ECD\u5728\u3002"],
  "design.unknown.name": ["Unknown kept, never rerun", "unknown \u4FDD\u7559\u4E0D\u91CD\u8DD1"],
  "design.unknown.pain": ["A stalled provider gets rerun quietly or counted as success.", "\u4F9B\u5E94\u5546\u5361\u4F4F\u540E\u88AB\u6084\u6084\u91CD\u8DD1\uFF0C\u6216\u88AB\u5F53\u6210\u6210\u529F\u3002"],
  "design.unknown.how": ["The stalled attempt settles as unknown, stays on record, is never relaunched.", "\u5361\u4F4F\u7684\u5C1D\u8BD5\u7ED3\u7B97\u4E3A unknown\uFF0C\u7559\u5728\u8D26\u672C\u91CC\uFF0C\u4E0D\u518D\u53D1\u8D77\u3002"],
  "design.idempotent.name": ["Idempotent execution", "\u5E42\u7B49\u6267\u884C"],
  "design.idempotent.pain": ["A retry repeats the side effect.", "\u91CD\u8BD5\u628A\u526F\u4F5C\u7528\u505A\u4E86\u4E24\u904D\u3002"],
  "design.idempotent.how": ["The same key returns the original receipt. No second effect.", "\u540C\u4E00\u4E2A\u952E\u8FD4\u56DE\u539F\u56DE\u6267\uFF0C\u4E0D\u4EA7\u751F\u7B2C\u4E8C\u6B21\u6548\u679C\u3002"],
  "design.knowledge.name": ["User knowledge and context budget", "\u7528\u6237\u77E5\u8BC6\u5E93\u4E0E\u4E0A\u4E0B\u6587\u9884\u7B97"],
  "design.knowledge.pain": ["Context overflows and nobody can say what was cut.", "\u4E0A\u4E0B\u6587\u88C5\u4E0D\u4E0B\uFF0C\u4E5F\u8BF4\u4E0D\u6E05\u820D\u6389\u4E86\u4EC0\u4E48\u3002"],
  "design.knowledge.how": ["Versioned sources, token budget, feedback scoring. Not wired to the core RPC.", "\u7248\u672C\u5316\u6765\u6E90\u3001token \u9884\u7B97\u3001\u53CD\u9988\u6253\u5206\uFF1B\u5C1A\u672A\u63A5\u5165\u6838\u5FC3 RPC\u3002"],
  "design.forged.name": ["Recomputation rejects forged results", "\u72EC\u7ACB\u590D\u7B97\u62D2\u7EDD\u4F2A\u9020\u7ED3\u679C"],
  "design.forged.pain": ["A model-reported result cannot be taken at face value.", "\u6A21\u578B\u81EA\u62A5\u7684\u7ED3\u679C\u4E0D\u80FD\u76F4\u63A5\u76F8\u4FE1\u3002"],
  "design.forged.how": ["The checker recomputes from a closed form. A forged alpha 0.9 is rejected.", "\u68C0\u67E5\u5668\u6309\u95ED\u5F0F\u89E3\u72EC\u7ACB\u590D\u7B97\uFF1B\u4F2A\u9020\u7684 alpha 0.9 \u88AB\u62D2\u3002"],
  "design.human.name": ["Human-only approval, bound to a snapshot digest", "\u4EBA\u5DE5\u4E13\u5C5E\u5BA1\u6279\uFF0C\u7ED1\u5B9A\u5FEB\u7167\u6458\u8981"],
  "design.human.pain": ["A machine could approve its own work.", "\u673A\u5668\u53EF\u80FD\u81EA\u5DF1\u6279\u51C6\u81EA\u5DF1\u7684\u7ED3\u679C\u3002"],
  "design.human.how": ["The machine channel cannot decide. A person types the first 8 digest characters in a terminal.", "\u673A\u5668\u901A\u9053\u4E0D\u80FD\u51B3\u5B9A\uFF1B\u4EBA\u5728\u7EC8\u7AEF\u8F93\u5165\u6458\u8981\u524D 8 \u4F4D\u3002"],
  "design.rules.name": ["Rules only tighten", "\u89C4\u5219\u53EA\u6536\u7D27"],
  "design.rules.pain": ["A rule edit quietly loosens a guard.", "\u6539\u4E00\u6761\u89C4\u5219\u5C31\u6084\u6084\u653E\u677E\u4E86\u628A\u5173\u3002"],
  "design.rules.how": ["Deny, require human, warn. No allow. An unknown fact never passes a deny rule.", "\u53EA\u6709\u62D2\u7EDD\u3001\u9700\u4EBA\u5DE5\u3001\u8B66\u544A\uFF0C\u6CA1\u6709\u653E\u884C\uFF1B\u672A\u77E5\u4E8B\u5B9E\u8FC7\u4E0D\u4E86\u62D2\u7EDD\u89C4\u5219\u3002"],
  "design.voided.name": ["Changed candidate voids the approval", "\u5019\u9009\u53D8\u66F4\u4F5C\u5E9F\u5BA1\u6279"],
  "design.voided.pain": ["The content is swapped after the approval.", "\u5BA1\u6279\u4E4B\u540E\u5185\u5BB9\u88AB\u6362\u6389\u3002"],
  "design.voided.how": ["Changing the candidate supersedes the earlier approval.", "\u5019\u9009\u4E00\u53D8\uFF0C\u5148\u524D\u7684\u5BA1\u6279\u88AB\u53D6\u4EE3\u3002"],
  "design.reconcile.name": ["Delivery reconcile never replays", "\u4EA4\u4ED8\u5BF9\u8D26\u4E0D\u91CD\u653E"],
  "design.reconcile.pain": ["Reconciling replays a write that already landed.", "\u5BF9\u8D26\u65F6\u628A\u5DF2\u7ECF\u843D\u5730\u7684\u5199\u5165\u53C8\u6267\u884C\u4E00\u904D\u3002"],
  "design.reconcile.how": ["Applied is observed. Reconcile never replays the write.", "\u300C\u5DF2\u5E94\u7528\u300D\u9760\u89C2\u5BDF\u5F97\u5230\uFF1B\u5BF9\u8D26\u4E0D\u91CD\u653E\u5199\u5165\u3002"],
  "design.readmodel.name": ["Read models with watermarks", "\u7ED3\u6784\u5316\u8BFB\u6A21\u578B\u4E0E\u6C34\u4F4D"],
  "design.readmodel.pain": ["You cannot tell how fresh what you see is.", "\u770B\u5230\u7684\u6570\u636E\u4E0D\u77E5\u9053\u65B0\u4E0D\u65B0\u3002"],
  "design.readmodel.how": ["Every read carries a watermark, completeness and gaps.", "\u6BCF\u6B21\u8BFB\u53D6\u90FD\u5E26\u6C34\u4F4D\u3001\u5B8C\u6574\u5EA6\u548C\u7F3A\u53E3\u3002"],
  "design.tree.name": ["Module tree, 23 nodes", "\u6A21\u5757\u6811\u77E5\u8BC6\u56FE\uFF0823 \u8282\u70B9\uFF09"],
  "design.tree.pain": ["Module relationships live in people\u2019s heads.", "\u6A21\u5757\u4E4B\u95F4\u7684\u5173\u7CFB\u53EA\u5B58\u5728\u4E8E\u4EBA\u7684\u8111\u5B50\u91CC\u3002"],
  "design.tree.how": ["A documented tree with dependencies, browsable in Structure.", "\u6587\u6863\u58F0\u660E\u7684\u6A21\u5757\u6811\u4E0E\u4F9D\u8D56\uFF0C\u53EF\u5728\u300C\u7ED3\u6784\u300D\u91CC\u6D4F\u89C8\u3002"],
  "design.panel.name": ["Process panel", "\u8FC7\u7A0B\u53EF\u89C6\u5316\u9762\u677F"],
  "design.panel.pain": ["The run is only visible in logs.", "\u6267\u884C\u8FC7\u7A0B\u53EA\u80FD\u7FFB\u65E5\u5FD7\u3002"],
  "design.panel.how": ["A side panel in AGH reads 13 read-only services.", "AGH \u4FA7\u680F\u9762\u677F\u8BFB\u53D6 13 \u4E2A\u53EA\u8BFB\u670D\u52A1\u3002"],
  "design.plugin.name": ["Plugin mount", "\u63D2\u4EF6\u5316\u6302\u8F7D"],
  "design.plugin.pain": ["Kernel and host are welded together.", "\u5185\u6838\u548C\u5BBF\u4E3B\u710A\u6B7B\u5728\u4E00\u8D77\u3002"],
  "design.plugin.how": ["Mounted over stdio JSON-RPC (not MCP). Verified on AGH only.", "\u7ECF stdio JSON-RPC \u6302\u8F7D\uFF08\u4E0D\u662F MCP\uFF09\uFF0C\u76EE\u524D\u53EA\u5728 AGH \u4E0A\u9A8C\u8BC1\u3002"],
  "design.skill.name": ["Skill versions and four-way scoring", "Skill \u7248\u672C\u4E0E\u56DB\u7EF4\u8BC4\u5206"],
  "design.skill.pain": ["No basis for judging a skill.", "\u4E00\u4E2A Skill \u597D\u4E0D\u597D\u6CA1\u6709\u4F9D\u636E\u3002"],
  "design.skill.how": ["The registry holds versions and scope. The four scores are only a design.", "\u767B\u8BB0\u8868\u5DF2\u6709\u7248\u672C\u4E0E\u8303\u56F4\uFF1B\u56DB\u7EF4\u8BC4\u5206\u53EA\u662F\u8BBE\u8BA1\u3002"],
  "design.exchange.name": ["Traceable exchange between models", "\u6A21\u578B\u95F4\u53EF\u6EAF\u6E90\u4EA4\u6362"],
  "design.exchange.pain": ["Model-to-model questions cannot be traced.", "\u6A21\u578B\u4E4B\u95F4\u7684\u95EE\u7B54\u65E0\u6CD5\u8FFD\u6EAF\u3002"],
  "design.exchange.how": ["Exchanges and their basis are recorded. A reply points to a source version.", "\u4EA4\u6362\u5185\u5BB9\u4E0E\u4F9D\u636E\u5165\u8D26\uFF0C\u56DE\u590D\u8981\u80FD\u5B9A\u4F4D\u6765\u6E90\u7248\u672C\u3002"],
  "design.workspace.name": ["Workspace and multi-project", "\u5DE5\u4F5C\u533A\u4E0E\u591A\u9879\u76EE"],
  "design.workspace.pain": ["Every project is an island.", "\u6BCF\u4E2A\u9879\u76EE\u90FD\u662F\u5B64\u5C9B\u3002"],
  "design.workspace.how": ["A workspace manages several project stores. Kernel commands do not exist yet.", "\u5DE5\u4F5C\u533A\u7BA1\u7406\u591A\u4E2A\u9879\u76EE\u5E93\uFF1B\u5185\u6838\u547D\u4EE4\u5C1A\u672A\u5B9E\u73B0\u3002"]
};
var messages = {
  en: Object.fromEntries(Object.entries(entries).map(([key, values]) => [key, values[0]])),
  "zh-CN": Object.fromEntries(Object.entries(entries).map(([key, values]) => [key, values[1]]))
};
function createTranslator(locale = "zh-CN") {
  const value = typeof locale === "string" ? locale : locale?.locale || locale?.language || locale?.code || "zh-CN";
  const dictionary = messages[String(value).toLowerCase().startsWith("en") ? "en" : "zh-CN"];
  return (key, variables = {}) => String(dictionary[key] ?? messages.en[key] ?? key).replace(/\{([\w]+)\}/g, (match, name) => variables[name] == null ? match : String(variables[name]));
}

// client/src/parts/Primitives.jsx
import React, { useRef } from "react";
import { Fragment, jsx, jsxs } from "react/jsx-runtime";
var array = (value) => Array.isArray(value) ? value : [];
var textValue = (value, t) => value == null || value === "" ? t("common.unknown") : typeof value === "object" ? JSON.stringify(value) : String(value);
var stagger = (index) => `pk-enter pk-i-${Math.min(index, 15)}`;
function useArrivals(keys) {
  const seen = useRef(null);
  const arrived = useRef(/* @__PURE__ */ new Set());
  if (seen.current === null) {
    if (keys.length) seen.current = new Set(keys);
  } else {
    for (const key of keys) if (!seen.current.has(key)) {
      seen.current.add(key);
      arrived.current.add(key);
    }
  }
  return arrived.current;
}
function Info({ text, label }) {
  if (!text) return null;
  return /* @__PURE__ */ jsx("span", { className: "pk-info", tabIndex: 0, role: "note", "aria-label": label ? `${label}: ${text}` : text, "data-tip": text, children: "i" });
}
var SOURCE_GLYPH = { live: "\u25CF", document: "\u25A4", derived: "\u2248", preview: "\u25C7" };
function SourceTag({ kind = "live", source, t }) {
  kind = source || kind;
  return /* @__PURE__ */ jsxs("span", { className: `pk-source pk-source-${kind}`, "data-source": kind, "data-tip": t(`source.${kind}Tip`), "data-edge": "end", tabIndex: 0, children: [
    /* @__PURE__ */ jsx("span", { "aria-hidden": "true", children: SOURCE_GLYPH[kind] ?? "\xB7" }),
    t(`source.${kind}`)
  ] });
}
function Section({ title, source = "live", t, children, className = "", hint, aside }) {
  return /* @__PURE__ */ jsxs("section", { className: `pk-section ${source === "preview" ? "pk-preview" : ""} ${className}`, "data-source": source, children: [
    /* @__PURE__ */ jsxs("header", { className: "pk-section-head", children: [
      /* @__PURE__ */ jsx("h3", { children: title }),
      /* @__PURE__ */ jsx(Info, { text: hint }),
      aside,
      /* @__PURE__ */ jsx(SourceTag, { kind: source, t })
    ] }),
    children
  ] });
}
function EmptyState({ t, message, kind = "empty" }) {
  return /* @__PURE__ */ jsxs("div", { className: `pk-state pk-state-${kind}`, role: kind === "error" ? "alert" : "status", children: [
    /* @__PURE__ */ jsx("span", { className: "pk-state-icon", "aria-hidden": "true", children: kind === "loading" ? "\u25CC" : kind === "error" ? "!" : "\u25CB" }),
    /* @__PURE__ */ jsx("p", { children: message || t(kind === "loading" ? "status.loading" : kind === "error" ? "status.unavailable" : "status.noData") })
  ] });
}
function ResourceState({ resource, t, empty: empty2 = false, emptyText, children, disabledText, source = "live" }) {
  const phase = resource?.phase || "loading";
  if (phase === "disabled") return /* @__PURE__ */ jsx(EmptyState, { t, message: disabledText || t("common.queryPrompt") });
  if (phase === "loading" && resource?.data == null) return /* @__PURE__ */ jsx(EmptyState, { t, kind: "loading" });
  if ((phase === "error" || phase === "unavailable") && resource?.data == null) return /* @__PURE__ */ jsxs("div", { children: [
    /* @__PURE__ */ jsx(EmptyState, { t, kind: "error", message: /(active session|services? capability|client service is unavailable)/i.test(String(resource?.error || "")) ? t("shell.sessionRequired") : void 0 }),
    resource?.error && /* @__PURE__ */ jsx("p", { className: "pk-error-detail", children: /* @__PURE__ */ jsx("code", { children: textValue(resource.error, t) }) })
  ] });
  const meta = resource.meta;
  const gaps = [...array(meta?.gaps), ...array(meta?.required_missing)];
  const documentation = source === "document" || meta?.origin_kind === "documentation";
  const fresh = meta?.freshness || {};
  const stale = phase === "error" || phase === "unavailable" || gaps.length > 0 || !documentation && (fresh.projection_stale === true || Number(fresh.projection_lag_seq || 0) > 0 || ["stale", "source_failed", "incomplete"].includes(fresh.state) || ["incomplete", "unknown"].includes(meta?.completeness));
  const noData = phase === "empty" || resource?.data == null || empty2;
  return /* @__PURE__ */ jsxs(Fragment, { children: [
    stale && /* @__PURE__ */ jsxs("div", { className: "pk-stale-banner", role: "status", children: [
      /* @__PURE__ */ jsx("span", { "aria-hidden": "true", children: "\u25B3" }),
      /* @__PURE__ */ jsx("strong", { children: t(documentation ? "status.documentGaps" : "status.stale") }),
      resource.error && /* @__PURE__ */ jsx("span", { children: textValue(resource.error, t) }),
      gaps.length > 0 && /* @__PURE__ */ jsxs("details", { children: [
        /* @__PURE__ */ jsx("summary", { children: t("shell.gaps", { count: gaps.length }) }),
        /* @__PURE__ */ jsx("ul", { children: gaps.map((gap, i) => /* @__PURE__ */ jsx("li", { children: /* @__PURE__ */ jsx("code", { children: textValue(gap, t) }) }, i)) })
      ] })
    ] }),
    noData ? /* @__PURE__ */ jsx(EmptyState, { t, message: emptyText }) : children
  ] });
}
var KNOWN_STATUS = /* @__PURE__ */ new Set(["completed", "failed", "unknown", "running", "starting", "cancelled", "interrupted", "pending", "approved", "rejected", "expired", "prepared", "claimed", "applying", "applied", "selected", "not_checked", "satisfied", "missing", "too_old", "ok", "passed", "not_validated", "limited_evidence", "review_required", "trial"]);
function Badge({ value = "unknown", t }) {
  const status = typeof value === "string" ? value : "unknown";
  return /* @__PURE__ */ jsx("span", { className: "pk-badge", "data-status": status, children: KNOWN_STATUS.has(status) ? t(`status.${status}`) : status });
}
var VERDICT_GLYPH = { passed: "\u2713", failed: "\u2715", unknown: "?", human: "\u25D0", open: "\u25CB" };
function verdictOf(attempt) {
  const result = attempt?.verification_result;
  const checked = typeof result === "string" ? result : result && typeof result === "object" ? result.passed === true ? "passed" : result.passed === false ? "failed" : result.status ?? result.result ?? null : null;
  if (attempt?.status === "failed" || checked === "failed") return "failed";
  if (attempt?.status === "unknown" || !attempt?.status) return "unknown";
  if (checked === "passed") return "passed";
  return "open";
}
function Verdict({ value = "open", t, size = "md", stamp = false }) {
  const verdict = VERDICT_GLYPH[value] ? value : "open";
  return /* @__PURE__ */ jsx(Fragment, { children: /* @__PURE__ */ jsxs("span", { className: `pk-verdict pk-verdict-${size}`, "data-verdict": verdict, "data-stamp": stamp ? "true" : "false", "data-tip": t(`verdict.${verdict}.tip`), tabIndex: 0, children: [
    /* @__PURE__ */ jsx("span", { className: "pk-verdict-glyph", "aria-hidden": "true", children: VERDICT_GLYPH[verdict] }),
    /* @__PURE__ */ jsx("span", { className: "pk-verdict-label", children: t(`verdict.${verdict}`) })
  ] }, verdict) });
}
function Ticker({ value }) {
  return /* @__PURE__ */ jsx(Fragment, { children: /* @__PURE__ */ jsx("span", { className: "pk-tick", children: value }, String(value)) });
}
function Stat({ label, value, index = 0, tone }) {
  return /* @__PURE__ */ jsxs("div", { className: `pk-stat ${stagger(index)}`, "data-tone": tone, children: [
    /* @__PURE__ */ jsx("strong", { className: "pk-number", children: /* @__PURE__ */ jsx(Ticker, { value }) }),
    /* @__PURE__ */ jsx("span", { children: label })
  ] });
}
function Fields({ values, t }) {
  return /* @__PURE__ */ jsx("dl", { className: "pk-fields", children: values.map(([label, value]) => /* @__PURE__ */ jsxs("div", { children: [
    /* @__PURE__ */ jsx("dt", { children: label }),
    /* @__PURE__ */ jsx("dd", { children: textValue(value, t) })
  ] }, label)) });
}
function DataList({ items, t }) {
  return array(items).length ? /* @__PURE__ */ jsx("ul", { className: "pk-data-list", children: array(items).map((item, i) => /* @__PURE__ */ jsx("li", { className: stagger(i), children: /* @__PURE__ */ jsx("code", { children: textValue(item, t) }) }, i)) }) : /* @__PURE__ */ jsx("p", { className: "pk-quiet", children: t("common.none") });
}
function ViewTitle({ id, t, subtitle, children }) {
  return /* @__PURE__ */ jsxs("header", { className: "pk-view-heading", children: [
    /* @__PURE__ */ jsxs("div", { children: [
      /* @__PURE__ */ jsx("h2", { children: t(`navigation.${id}`) }),
      subtitle && /* @__PURE__ */ jsx("p", { children: subtitle })
    ] }),
    children
  ] });
}
var shortId = (value, size = 8) => {
  const text = String(value ?? "");
  const tail = text.split("-").pop();
  return tail.length > size ? tail.slice(-size) : tail || text;
};

// client/src/views/Overview.jsx
import React2 from "react";

// client/src/views/helpers.js
function phaseOf(attempts, selected, approvals, operation) {
  const queue = array(approvals);
  const matchingApproval = queue.some((item) => item.approval_id === operation?.approval_id && item.snapshot_id === operation?.snapshot_id);
  if (selected && matchingApproval && operation?.operation_kind === "delivery" && operation.status === "applied") return 5;
  if (queue.some((item) => item.status === "pending" || item.status === "approved")) return 4;
  if (selected) return 3;
  if (array(attempts).some((attempt) => attempt.verification_result !== void 0 && attempt.verification_result !== null)) return 2;
  if (array(attempts).length) return 1;
  return 0;
}
function finiteCount(value) {
  const number = Number(value);
  return Number.isFinite(number) && number >= 0 ? number : null;
}
function tally(items, getKey) {
  return array(items).reduce((counts, item) => {
    const key = String(getKey(item) ?? "unknown");
    counts[key] = (counts[key] || 0) + 1;
    return counts;
  }, {});
}
function moduleDegrees(nodes, nodeId) {
  const list = array(nodes);
  return {
    outgoing: array(list.find((node) => node.node_id === nodeId)?.depends_on).length,
    incoming: list.filter((node) => array(node.depends_on).includes(nodeId)).length
  };
}
function moduleNeighbours(nodes, nodeId) {
  const list = array(nodes);
  const node = list.find((item) => item.node_id === nodeId);
  const out = new Set(array(node?.depends_on));
  const incoming = new Set(list.filter((item) => array(item.depends_on).includes(nodeId)).map((item) => item.node_id));
  const related = new Set(array(node?.related_to));
  list.forEach((item) => {
    if (array(item.related_to).includes(nodeId)) related.add(item.node_id);
  });
  out.delete(nodeId);
  incoming.delete(nodeId);
  related.delete(nodeId);
  return { out, incoming, related };
}
function statusDistribution(compare) {
  return tally(compare?.attempts, (attempt) => attempt.status);
}
function fitOf(attempt) {
  const value = attempt?.alpha_fit ?? attempt?.verification_result?.alpha_fit;
  if (value == null || value === "") return null;
  return Number.isFinite(Number(value)) ? Number(value).toFixed(5) : String(value);
}
function reasonOf(attempt) {
  const value = attempt?.reason ?? attempt?.check_reason ?? attempt?.verification_result?.reason;
  return value == null || value === "" ? null : String(value);
}
function timelineFailureSeries(events) {
  const buckets = /* @__PURE__ */ new Map();
  for (const event of array(events)) {
    const type = String(event.event_type || "");
    if (!/(?:^|[._-])(?:failed|failure|unknown)(?:$|[._-])/.test(type)) continue;
    const seq = Number(event.commit_seq);
    if (!Number.isFinite(seq)) continue;
    const bucket = buckets.get(seq) || { seq, failed: 0, unknown: 0 };
    if (/(?:^|[._-])unknown(?:$|[._-])/.test(type)) bucket.unknown += 1;
    else bucket.failed += 1;
    buckets.set(seq, bucket);
  }
  return [...buckets.values()].sort((a, b) => a.seq - b.seq);
}

// client/src/views/Overview.jsx
import { Fragment as Fragment2, jsx as jsx2, jsxs as jsxs2 } from "react/jsx-runtime";
var STEPS = ["dispatch", "attempt", "verify", "select", "approval", "delivery"];
function Stepper({ active, t }) {
  return /* @__PURE__ */ jsxs2("div", { className: "pk-stepper", "data-at": active, children: [
    /* @__PURE__ */ jsx2("div", { className: "pk-stepper-rail", "aria-hidden": "true", children: /* @__PURE__ */ jsx2("span", { className: "pk-stepper-fill" }) }),
    /* @__PURE__ */ jsx2("ol", { className: "pk-steps", "aria-label": t("overview.workflow"), children: STEPS.map((step, i) => /* @__PURE__ */ jsxs2("li", { "data-tip": t(`step.${step}Hint`), "data-state": i === active ? "active" : i < active ? "observed" : "future", "aria-current": i === active ? "step" : void 0, children: [
      /* @__PURE__ */ jsx2("span", { className: "pk-step-dot", "aria-hidden": "true", children: i < active ? "\u2713" : i + 1 }),
      /* @__PURE__ */ jsx2("strong", { children: t(`step.${step}`) })
    ] }, step)) })
  ] });
}
var HEADLINE_COUNTS = ["attempt", "verification", "approval", "requirement"];
function Overview({ resources, t, navigate }) {
  const overview = resources.overview;
  const compare = resources.compare;
  const approvals = resources.approvals;
  const data = overview?.data || {};
  const attempts = array(compare?.data?.attempts);
  const selectedId = compare?.data?.selected?.attempt_id;
  const queue = array(approvals?.data?.queue);
  const pending = queue.filter((item) => item.status === "pending");
  const pendingCount = Number(approvals?.data?.pending_count ?? pending.length);
  const active = phaseOf(attempts, compare?.data?.selected, queue, resources.operation?.data);
  const counts = data.object_counts || {};
  const issues = [...array(data.blockers), ...array(data.source_gaps)];
  const arrived = useArrivals(attempts.map((attempt) => attempt.attempt_id));
  return /* @__PURE__ */ jsxs2("div", { className: "pk-view pk-overview", children: [
    /* @__PURE__ */ jsx2(ViewTitle, { id: "overview", t, subtitle: t("overview.subtitle") }),
    /* @__PURE__ */ jsxs2(Section, { title: t("overview.workflow"), t, source: "derived", hint: t("overview.inferred"), className: "pk-story", children: [
      /* @__PURE__ */ jsx2(ResourceState, { resource: compare, t, children: /* @__PURE__ */ jsx2(Stepper, { active, t }) }),
      queue.some((item) => item.status === "approved") && resources.operation?.data == null && /* @__PURE__ */ jsx2("p", { className: "pk-quiet", children: t("overview.deliveryUnknown") })
    ] }),
    pendingCount > 0 && /* @__PURE__ */ jsxs2("aside", { className: "pk-callout", "data-verdict": "human", role: "status", children: [
      /* @__PURE__ */ jsx2(Verdict, { value: "human", t, size: "lg" }),
      /* @__PURE__ */ jsxs2("div", { className: "pk-callout-body", children: [
        /* @__PURE__ */ jsx2("strong", { children: t("overview.pending", { count: pendingCount }) }),
        pending[0]?.snapshot_digest && /* @__PURE__ */ jsxs2("p", { children: [
          /* @__PURE__ */ jsx2("code", { className: "pk-digest-inline", children: String(pending[0].snapshot_digest).slice(0, 8) }),
          t("overview.pendingLine")
        ] })
      ] }),
      navigate && /* @__PURE__ */ jsx2("button", { type: "button", className: "pk-button pk-button-strong", onClick: () => navigate("permissions"), children: t("overview.openApprovals") })
    ] }),
    /* @__PURE__ */ jsx2(Section, { title: t("overview.currentAttempts"), t, children: /* @__PURE__ */ jsx2(ResourceState, { resource: compare, t, empty: !attempts.length, emptyText: t("execution.noAttempts"), children: /* @__PURE__ */ jsx2("ol", { className: "pk-attempt-strip", children: attempts.map((attempt, i) => {
      const verdict = verdictOf(attempt);
      const fit = fitOf(attempt);
      return /* @__PURE__ */ jsxs2("li", { className: `${stagger(i)} ${arrived.has(attempt.attempt_id) ? "pk-arrived" : ""}`, "data-verdict": verdict, "data-selected": attempt.attempt_id === selectedId ? "true" : "false", children: [
        /* @__PURE__ */ jsx2("span", { className: "pk-strip-strategy", children: attempt.strategy_id || "\u2014" }),
        /* @__PURE__ */ jsx2(Verdict, { value: verdict, t, stamp: true }),
        fit && /* @__PURE__ */ jsxs2("span", { className: "pk-strip-fit", children: [
          /* @__PURE__ */ jsx2("i", { children: t("execution.fit") }),
          " ",
          fit
        ] }),
        /* @__PURE__ */ jsx2("code", { className: "pk-strip-id", title: attempt.attempt_id, children: shortId(attempt.attempt_id) }),
        attempt.attempt_id === selectedId && /* @__PURE__ */ jsx2("span", { className: "pk-chip pk-chip-selected", children: t("status.selected") })
      ] }, attempt.attempt_id);
    }) }) }) }),
    /* @__PURE__ */ jsx2(Section, { title: t("overview.objects"), t, children: /* @__PURE__ */ jsxs2(ResourceState, { resource: overview, t, empty: !Object.keys(counts).length, children: [
      /* @__PURE__ */ jsxs2("div", { className: "pk-stats", children: [
        HEADLINE_COUNTS.filter((type) => counts[type] != null).map((type, i) => /* @__PURE__ */ jsx2(Stat, { label: t(`overview.count.${type}`), value: counts[type], index: i }, type)),
        /* @__PURE__ */ jsx2(Stat, { label: t("overview.lastCommit"), value: `#${data.last_commit_seq ?? "\u2014"}`, index: 4 })
      ] }),
      /* @__PURE__ */ jsxs2("details", { className: "pk-more", children: [
        /* @__PURE__ */ jsx2("summary", { children: t("overview.allObjects", { count: Object.keys(counts).length }) }),
        /* @__PURE__ */ jsx2("ul", { className: "pk-chip-list", children: Object.entries(counts).map(([type, count]) => /* @__PURE__ */ jsxs2("li", { className: "pk-chip", children: [
          /* @__PURE__ */ jsx2("code", { children: type }),
          /* @__PURE__ */ jsx2(Ticker, { value: count })
        ] }, type)) })
      ] }),
      /* @__PURE__ */ jsx2("p", { className: "pk-issues", "data-empty": issues.length ? "false" : "true", children: issues.length ? /* @__PURE__ */ jsxs2(Fragment2, { children: [
        /* @__PURE__ */ jsx2("span", { "aria-hidden": "true", children: "\u25B3" }),
        t("overview.issues", { count: issues.length }),
        /* @__PURE__ */ jsx2(Info, { text: issues.map((item) => typeof item === "string" ? item : JSON.stringify(item)).join("\n") })
      ] }) : /* @__PURE__ */ jsxs2(Fragment2, { children: [
        /* @__PURE__ */ jsx2("span", { "aria-hidden": "true", children: "\u2713" }),
        t("overview.noIssues")
      ] }) })
    ] }) })
  ] });
}

// client/src/views/Structure.jsx
import React4, { useMemo, useState as useState2 } from "react";

// client/src/parts/TraceGraph.jsx
import React3, { useState } from "react";
import { Fragment as Fragment3, jsx as jsx3, jsxs as jsxs3 } from "react/jsx-runtime";
function traceLayout(nodes) {
  const perDepth = /* @__PURE__ */ new Map();
  return array(nodes).map((node) => {
    const depth = Math.max(0, Number(node.depth) || 0);
    const index = perDepth.get(depth) || 0;
    perDepth.set(depth, index + 1);
    return { ...node, x: 110 + depth * 245, y: 70 + index * 100 };
  });
}
function TraceGraph({ data, t }) {
  const nodes = traceLayout(data.nodes);
  const byId = new Map(nodes.map((node) => [node.node_id, node]));
  const edges = array(data.edges);
  const width = Math.max(720, ...nodes.map((node) => node.x + 130));
  const height = Math.max(220, ...nodes.map((node) => node.y + 85));
  return /* @__PURE__ */ jsx3("div", { className: "pk-graph-scroll", children: /* @__PURE__ */ jsxs3("svg", { className: "pk-trace-graph", viewBox: `0 0 ${width} ${height}`, width, height, role: "img", "aria-label": t("trace.graphLabel"), children: [
    /* @__PURE__ */ jsx3("title", { children: t("trace.graphLabel") }),
    /* @__PURE__ */ jsx3("defs", { children: /* @__PURE__ */ jsx3("marker", { id: "pk-trace-arrow", markerWidth: "8", markerHeight: "8", refX: "7", refY: "3", orient: "auto", children: /* @__PURE__ */ jsx3("path", { d: "M0,0 L0,6 L8,3 z" }) }) }),
    edges.map((edge, i) => {
      const from = byId.get(edge.from);
      const to = byId.get(edge.to);
      if (!from || !to) return null;
      return /* @__PURE__ */ jsxs3("g", { className: "pk-trace-edge", children: [
        /* @__PURE__ */ jsx3("path", { d: `M${from.x + 95},${from.y} C${from.x + 160},${from.y} ${to.x - 160},${to.y} ${to.x - 95},${to.y}`, markerEnd: "url(#pk-trace-arrow)" }),
        /* @__PURE__ */ jsx3("text", { x: (from.x + to.x) / 2, y: (from.y + to.y) / 2 - 8, children: edge.relation }),
        /* @__PURE__ */ jsx3("title", { children: textValue(edge.path, t) })
      ] }, `${edge.from}:${edge.to}:${i}`);
    }),
    nodes.map((node) => /* @__PURE__ */ jsxs3("g", { className: "pk-trace-node", "data-type": node.object_type, "data-missing": node.exists === false ? "true" : "false", transform: `translate(${node.x},${node.y})`, children: [
      /* @__PURE__ */ jsx3("rect", { x: "-95", y: "-27", width: "190", height: "58", rx: "10" }),
      /* @__PURE__ */ jsx3("text", { className: "pk-node-title", textAnchor: "middle", y: "-5", children: node.object_id || node.node_id }),
      /* @__PURE__ */ jsx3("text", { className: "pk-node-kind", textAnchor: "middle", y: "15", children: node.object_type }),
      /* @__PURE__ */ jsx3("title", { children: `${node.node_id} \xB7 ${node.revision_id || t("common.unknown")}` })
    ] }, node.node_id))
  ] }) });
}
function TracePanel({ resource, t, allowQuery = true }) {
  const [root, setRoot] = useState({ project_id: "", object_type: "", object_id: "", revision_id: "" });
  const [direction, setDirection] = useState("both");
  const [depth, setDepth] = useState(3);
  const [invalid, setInvalid] = useState(false);
  const data = resource?.data || {};
  const submit = (event) => {
    event.preventDefault();
    const filled = Object.values(root).filter((value) => value.trim()).length;
    if (filled !== 0 && filled !== 4) {
      setInvalid(true);
      return;
    }
    setInvalid(false);
    resource?.refresh?.({ root_ref: filled ? Object.fromEntries(Object.entries(root).map(([key, value]) => [key, value.trim()])) : void 0, direction, max_depth: Math.max(1, Math.min(20, Number(depth))) });
  };
  return /* @__PURE__ */ jsxs3(Fragment3, { children: [
    allowQuery && /* @__PURE__ */ jsxs3("details", { className: "pk-trace-query", children: [
      /* @__PURE__ */ jsx3("summary", { children: t("trace.queryTitle") }),
      /* @__PURE__ */ jsx3("p", { className: "pk-note", children: t("trace.queryHint") }),
      /* @__PURE__ */ jsxs3("form", { className: "pk-query-form pk-trace-form", onSubmit: submit, children: [
        Object.keys(root).map((key) => /* @__PURE__ */ jsxs3("label", { children: [
          t(`trace.${key}`),
          /* @__PURE__ */ jsx3("input", { value: root[key], maxLength: 128, onChange: (event) => setRoot({ ...root, [key]: event.target.value }) })
        ] }, key)),
        /* @__PURE__ */ jsxs3("label", { children: [
          t("trace.direction"),
          /* @__PURE__ */ jsx3("select", { value: direction, onChange: (event) => setDirection(event.target.value), children: ["both", "incoming", "outgoing"].map((value) => /* @__PURE__ */ jsx3("option", { value, children: t(`trace.${value}`) }, value)) })
        ] }),
        /* @__PURE__ */ jsxs3("label", { children: [
          t("trace.depth"),
          /* @__PURE__ */ jsx3("input", { type: "number", value: depth, min: "1", max: "20", required: true, onChange: (event) => setDepth(event.target.value) })
        ] }),
        /* @__PURE__ */ jsx3("button", { className: "pk-button", type: "submit", children: t("common.query") }),
        invalid && /* @__PURE__ */ jsx3("p", { className: "pk-note pk-note-warn", role: "alert", children: t("trace.fullRootRequired") })
      ] })
    ] }),
    /* @__PURE__ */ jsxs3(ResourceState, { resource, t, empty: !array(data.nodes).length, children: [
      data.truncated && /* @__PURE__ */ jsx3("p", { className: "pk-note pk-note-warn", children: t("trace.truncated") }),
      /* @__PURE__ */ jsx3(Fields, { t, values: [[t("trace.root"), data.root], [t("trace.nodeCount"), data.node_count], [t("trace.edgeCount"), data.edge_count]] }),
      /* @__PURE__ */ jsx3(TraceGraph, { data, t }),
      /* @__PURE__ */ jsxs3("details", { className: "pk-trace-records", children: [
        /* @__PURE__ */ jsx3("summary", { children: t("trace.records") }),
        /* @__PURE__ */ jsx3("div", { className: "pk-table-wrap", children: /* @__PURE__ */ jsxs3("table", { children: [
          /* @__PURE__ */ jsx3("thead", { children: /* @__PURE__ */ jsxs3("tr", { children: [
            /* @__PURE__ */ jsx3("th", { children: t("trace.object_id") }),
            /* @__PURE__ */ jsx3("th", { children: t("trace.object_type") }),
            /* @__PURE__ */ jsx3("th", { children: t("trace.relation") }),
            /* @__PURE__ */ jsx3("th", { children: t("trace.revision_id") }),
            /* @__PURE__ */ jsx3("th", { children: t("trace.exists") })
          ] }) }),
          /* @__PURE__ */ jsx3("tbody", { children: array(data.nodes).map((node) => /* @__PURE__ */ jsxs3("tr", { children: [
            /* @__PURE__ */ jsx3("td", { children: /* @__PURE__ */ jsx3("code", { children: node.object_id }) }),
            /* @__PURE__ */ jsx3("td", { children: node.object_type }),
            /* @__PURE__ */ jsx3("td", { children: node.relation }),
            /* @__PURE__ */ jsx3("td", { children: /* @__PURE__ */ jsx3("code", { children: node.revision_id }) }),
            /* @__PURE__ */ jsx3("td", { children: node.exists === false ? t("common.no") : node.exists === true ? t("common.yes") : t("common.unknown") })
          ] }, node.node_id)) })
        ] }) })
      ] })
    ] })
  ] });
}

// client/src/views/Structure.jsx
import { jsx as jsx4, jsxs as jsxs4 } from "react/jsx-runtime";
function computeAllDegrees(nodes) {
  const incoming = /* @__PURE__ */ new Map();
  const outgoing = /* @__PURE__ */ new Map();
  nodes.forEach((n) => {
    incoming.set(n.node_id, 0);
    outgoing.set(n.node_id, array(n.depends_on).length);
  });
  nodes.forEach((n) => {
    array(n.depends_on).forEach((id) => {
      if (incoming.has(id)) incoming.set(id, incoming.get(id) + 1);
    });
  });
  return { incoming, outgoing };
}
function NodeCard({ node, t, openDocument, inDeg = 0, outDeg = 0 }) {
  const facts = node.facts || {};
  const requirementIds = array(facts.requirement_ids);
  const recordCounts = facts.linked_records || {};
  const totalLinks = Object.values(recordCounts).reduce((sum, arr) => sum + (Array.isArray(arr) ? arr.length : 0), 0);
  const conversations = array(node.conversation_refs);
  return /* @__PURE__ */ jsxs4("article", { className: "pk-node-card", children: [
    /* @__PURE__ */ jsxs4("header", { children: [
      /* @__PURE__ */ jsxs4("div", { children: [
        /* @__PURE__ */ jsx4("code", { className: "pk-node-id", children: node.node_id }),
        /* @__PURE__ */ jsx4("span", { className: "pk-node-kind-label", children: node.node_kind })
      ] }),
      facts.document_version && /* @__PURE__ */ jsxs4("span", { className: "pk-version-badge", children: [
        "v",
        facts.document_version
      ] })
    ] }),
    facts.title && /* @__PURE__ */ jsx4("h4", { children: facts.title }),
    node.document && /* @__PURE__ */ jsx4("p", { className: "pk-node-doc-link", children: /* @__PURE__ */ jsx4("button", { type: "button", className: "pk-text-button", onClick: () => openDocument(`docs/modules/${node.document}`), children: node.document }) }),
    /* @__PURE__ */ jsxs4("dl", { className: "pk-node-facts", children: [
      facts.implementation_status && /* @__PURE__ */ jsxs4("div", { children: [
        /* @__PURE__ */ jsx4("dt", { children: t("structure.status") }),
        /* @__PURE__ */ jsx4("dd", { children: facts.implementation_status })
      ] }),
      facts.updated_at && /* @__PURE__ */ jsxs4("div", { children: [
        /* @__PURE__ */ jsx4("dt", { children: t("structure.updated") }),
        /* @__PURE__ */ jsx4("dd", { children: facts.updated_at })
      ] }),
      facts.source_revision && /* @__PURE__ */ jsxs4("div", { children: [
        /* @__PURE__ */ jsx4("dt", { children: t("structure.revision") }),
        /* @__PURE__ */ jsx4("dd", { children: /* @__PURE__ */ jsx4("code", { children: facts.source_revision }) })
      ] }),
      /* @__PURE__ */ jsxs4("div", { children: [
        /* @__PURE__ */ jsx4("dt", { children: t("structure.couplingDegree") }),
        /* @__PURE__ */ jsxs4("dd", { className: "pk-degree-chips", children: [
          /* @__PURE__ */ jsx4("span", { className: "pk-degree-chip pk-degree-in", "data-tip": t("structure.degreeIncoming"), tabIndex: 0, children: t("structure.inLabel", { n: inDeg }) }),
          /* @__PURE__ */ jsx4("span", { className: "pk-degree-chip pk-degree-out", "data-tip": t("structure.degreeOutgoing"), tabIndex: 0, children: t("structure.outLabel", { n: outDeg }) }),
          /* @__PURE__ */ jsx4(Info, { text: t("structure.degreeHint") })
        ] })
      ] }),
      requirementIds.length > 0 && /* @__PURE__ */ jsxs4("div", { children: [
        /* @__PURE__ */ jsx4("dt", { children: t("structure.requirements") }),
        /* @__PURE__ */ jsx4("dd", { className: "pk-req-list", children: requirementIds.map((reqId) => /* @__PURE__ */ jsx4(
          "button",
          {
            type: "button",
            className: "pk-req-chip",
            onClick: () => openDocument("docs/requirements/" + reqId + ".md"),
            title: t("structure.openReq", { id: reqId }),
            children: reqId
          },
          reqId
        )) })
      ] }),
      totalLinks > 0 && /* @__PURE__ */ jsxs4("div", { children: [
        /* @__PURE__ */ jsx4("dt", { children: t("structure.linkedRecords") }),
        /* @__PURE__ */ jsx4("dd", { children: /* @__PURE__ */ jsx4("span", { className: "pk-count-badge", children: totalLinks }) })
      ] })
    ] }),
    conversations.length > 0 ? /* @__PURE__ */ jsxs4("div", { className: "pk-conversation-refs", children: [
      /* @__PURE__ */ jsx4("h5", { children: t("structure.conversations") }),
      /* @__PURE__ */ jsx4("ul", { className: "pk-conv-list", children: conversations.map((ref) => /* @__PURE__ */ jsx4("li", { children: ref.endsWith(".md") ? /* @__PURE__ */ jsx4("button", { type: "button", className: "pk-text-button", onClick: () => openDocument(ref), title: ref, children: ref.split("/").pop() }) : /* @__PURE__ */ jsx4("code", { children: ref }) }, ref)) })
    ] }) : /* @__PURE__ */ jsxs4("p", { className: "pk-note", children: [
      t("structure.noConversation"),
      /* @__PURE__ */ jsx4(Info, { text: t("structure.noConversationTip") })
    ] }),
    totalLinks > 0 && /* @__PURE__ */ jsxs4("div", { className: "pk-linked-records", children: [
      /* @__PURE__ */ jsx4("h5", { children: t("structure.linkedList") }),
      Object.entries(recordCounts).map(([kind, arr]) => Array.isArray(arr) && arr.length > 0 && /* @__PURE__ */ jsxs4("div", { children: [
        /* @__PURE__ */ jsxs4("strong", { children: [
          kind,
          ":"
        ] }),
        /* @__PURE__ */ jsx4("ul", { children: arr.map((path) => /* @__PURE__ */ jsx4("li", { children: path.endsWith(".md") ? /* @__PURE__ */ jsx4("button", { type: "button", className: "pk-text-button", onClick: () => openDocument(path), title: path, children: path.split("/").pop() }) : /* @__PURE__ */ jsx4("code", { title: path, children: path.split("/").pop() }) }, path)) })
      ] }, kind))
    ] })
  ] });
}
function ModuleBranch({ node, childrenByParent, expanded, setExpanded, selected, setSelected, t, openDocument, ancestry = [] }) {
  if (ancestry.includes(node.node_id)) return /* @__PURE__ */ jsxs4("li", { className: "pk-note pk-note-warn", children: [
    t("structure.cycle"),
    ": ",
    /* @__PURE__ */ jsx4("code", { children: node.node_id })
  ] });
  const children = childrenByParent.get(node.node_id) || [];
  const open = expanded.has(node.node_id);
  const facts = node.facts || {};
  return /* @__PURE__ */ jsxs4("li", { className: "pk-tree-node", "data-selected": selected === node.node_id ? "true" : "false", children: [
    /* @__PURE__ */ jsxs4("div", { className: "pk-tree-row", children: [
      children.length ? /* @__PURE__ */ jsx4("button", { className: "pk-tree-toggle", "aria-label": t(open ? "structure.collapse" : "structure.expand", { id: node.node_id }), "aria-expanded": open, onClick: () => {
        const next = new Set(expanded);
        open ? next.delete(node.node_id) : next.add(node.node_id);
        setExpanded(next);
      }, children: open ? "\u2212" : "+" }) : /* @__PURE__ */ jsx4("span", { className: "pk-tree-leaf", "aria-hidden": "true", children: "\xB7" }),
      /* @__PURE__ */ jsxs4("button", { className: "pk-tree-select", "aria-pressed": selected === node.node_id, onClick: () => setSelected(node.node_id), children: [
        /* @__PURE__ */ jsxs4("span", { className: "pk-tree-label", children: [
          /* @__PURE__ */ jsx4("code", { children: node.node_id }),
          /* @__PURE__ */ jsx4("small", { children: node.node_kind })
        ] }),
        facts.document_version && /* @__PURE__ */ jsxs4("span", { className: "pk-tree-version", children: [
          "v",
          facts.document_version
        ] })
      ] })
    ] }),
    children.length > 0 && open && /* @__PURE__ */ jsx4("ul", { children: children.map((child) => /* @__PURE__ */ jsx4(ModuleBranch, { node: child, childrenByParent, expanded, setExpanded, selected, setSelected, t, openDocument, ancestry: [...ancestry, node.node_id] }, child.node_id)) })
  ] });
}
function statusTone(status) {
  if (typeof status !== "string" || !status.trim()) return "unknown";
  if (/test|未装配|待接受|未行为验证|可选|未接线|无 runtime|无真实|未批准/i.test(status)) return "limited";
  if (/已实现|implemented|可用/i.test(status)) return "implemented";
  return "unknown";
}
var COLUMN = 250;
var ROW = 46;
var BOX = { width: 196, height: 34 };
function layoutTree(nodes) {
  const ids = new Set(nodes.map((node) => node.node_id));
  const children = /* @__PURE__ */ new Map();
  nodes.forEach((node) => {
    const parent = node.navigation_parent && ids.has(node.navigation_parent) ? node.navigation_parent : "";
    children.set(parent, [...children.get(parent) || [], node]);
  });
  const positions = /* @__PURE__ */ new Map();
  let row = 0;
  let depthMax = 0;
  const place = (node, depth, seen) => {
    if (seen.has(node.node_id) || positions.has(node.node_id)) return null;
    const next = new Set(seen).add(node.node_id);
    depthMax = Math.max(depthMax, depth);
    const ys = (children.get(node.node_id) || []).map((child) => place(child, depth + 1, next)).filter((y2) => y2 !== null);
    const y = ys.length ? (ys[0] + ys.at(-1)) / 2 : 30 + row++ * ROW;
    positions.set(node.node_id, { x: 20 + depth * COLUMN, y, depth });
    return y;
  };
  (children.get("") || []).forEach((node) => place(node, 0, /* @__PURE__ */ new Set()));
  nodes.forEach((node) => {
    if (!positions.has(node.node_id)) place(node, 0, /* @__PURE__ */ new Set());
  });
  return { positions, width: 40 + depthMax * COLUMN + BOX.width, height: Math.max(120, row * ROW + 20) };
}
function ModuleGraph({ nodes, selected, setSelected, t }) {
  const { positions, width, height } = useMemo(() => layoutTree(nodes), [nodes]);
  const active = nodes.find((node) => node.node_id === selected);
  const near = useMemo(() => moduleNeighbours(nodes, selected), [nodes, selected]);
  const associated = /* @__PURE__ */ new Set([selected, ...near.out, ...near.incoming, ...near.related]);
  const relationOf = (id) => id === selected ? "self" : near.out.has(id) ? "out" : near.incoming.has(id) ? "in" : near.related.has(id) ? "related" : "none";
  const edges = [
    ...[...near.out].map((id) => ({ from: selected, to: id, relation: "depends_on", dir: "out" })),
    ...[...near.incoming].map((id) => ({ from: id, to: selected, relation: "depends_on", dir: "in" })),
    ...[...near.related].map((id) => ({ from: selected, to: id, relation: "related_to", dir: "related" }))
  ];
  const anchor = (id, side) => {
    const p = positions.get(id);
    return p && { x: p.x + (side === "right" ? BOX.width : 0), y: p.y };
  };
  return /* @__PURE__ */ jsx4("div", { className: "pk-graph-scroll", children: /* @__PURE__ */ jsxs4("svg", { className: "pk-module-graph", viewBox: `0 0 ${width} ${height}`, width, height, role: "group", "aria-label": t("structure.graph"), children: [
    /* @__PURE__ */ jsx4("title", { children: t("structure.graph") }),
    nodes.map((node) => {
      const from = anchor(node.navigation_parent, "right");
      const to = anchor(node.node_id, "left");
      if (!from || !to) return null;
      const mid = (from.x + to.x) / 2;
      return /* @__PURE__ */ jsx4("path", { className: "pk-tree-edge", "data-active": node.navigation_parent === selected || node.node_id === selected ? "true" : "false", d: `M${from.x},${from.y} C${mid},${from.y} ${mid},${to.y} ${to.x},${to.y}` }, `tree:${node.node_id}`);
    }),
    active && edges.map((edge) => {
      const from = positions.get(edge.from);
      const to = positions.get(edge.to);
      if (!from || !to || edge.from === edge.to) return null;
      const a = { x: from.x + BOX.width / 2, y: from.y };
      const b = { x: to.x + BOX.width / 2, y: to.y };
      const bend = Math.max(40, Math.abs(a.y - b.y) / 3);
      const side = a.x === b.x ? 1 : Math.sign(b.x - a.x);
      return /* @__PURE__ */ jsxs4("g", { className: `pk-module-edge pk-edge-${edge.relation}`, "data-dir": edge.dir, children: [
        /* @__PURE__ */ jsx4("path", { d: `M${a.x},${a.y} Q${(a.x + b.x) / 2 + bend * side},${(a.y + b.y) / 2} ${b.x},${b.y}` }),
        /* @__PURE__ */ jsxs4("title", { children: [
          edge.from,
          " ",
          t(edge.relation === "depends_on" ? "structure.dependency" : "structure.related"),
          " ",
          edge.to
        ] })
      ] }, `${edge.relation}:${edge.from}:${edge.to}`);
    }),
    nodes.map((node) => {
      const pos = positions.get(node.node_id);
      if (!pos) return null;
      const facts = node.facts || {};
      return /* @__PURE__ */ jsxs4(
        "g",
        {
          className: "pk-module-node",
          transform: `translate(${pos.x},${pos.y - BOX.height / 2})`,
          role: "button",
          tabIndex: 0,
          "aria-label": node.node_id,
          "aria-pressed": selected === node.node_id,
          "data-selected": selected === node.node_id ? "true" : "false",
          "data-associated": associated.has(node.node_id) ? "true" : "false",
          "data-rel": relationOf(node.node_id),
          "data-tone": statusTone(facts.implementation_status),
          "data-kind": node.node_kind,
          onClick: () => setSelected(node.node_id),
          onKeyDown: (event) => {
            if (event.key === "Enter" || event.key === " ") {
              event.preventDefault();
              setSelected(node.node_id);
            }
          },
          children: [
            /* @__PURE__ */ jsx4("rect", { width: BOX.width, height: BOX.height, rx: "8" }),
            /* @__PURE__ */ jsx4("rect", { className: "pk-node-tone", width: "4", height: BOX.height, rx: "2" }),
            /* @__PURE__ */ jsx4("text", { x: "12", y: "15", children: node.node_id }),
            /* @__PURE__ */ jsx4("text", { className: "pk-node-kind", x: "12", y: "28", children: facts.title || node.node_kind }),
            facts.document_version && /* @__PURE__ */ jsxs4("text", { className: "pk-node-version", x: BOX.width - 8, y: "15", textAnchor: "end", children: [
              "v",
              facts.document_version
            ] }),
            /* @__PURE__ */ jsx4("title", { children: [node.node_id, facts.title, facts.implementation_status, node.document].filter(Boolean).join(" \xB7 ") })
          ]
        },
        node.node_id
      );
    })
  ] }) });
}
function Structure({ resources, t, openDocument }) {
  const tree = resources.tree;
  const nodes = array(tree?.data?.nodes);
  const [selected, setSelected] = useState2("K-ROOT");
  const [expanded, setExpanded] = useState2(() => /* @__PURE__ */ new Set(["K-ROOT", "K-CORE", "K-DATA", "K-EXTENSIONS"]));
  const childrenByParent = useMemo(() => {
    const map = /* @__PURE__ */ new Map();
    nodes.forEach((node) => {
      const key = node.navigation_parent || "";
      map.set(key, [...map.get(key) || [], node]);
    });
    return map;
  }, [tree?.data]);
  const ids = new Set(nodes.map((node) => node.node_id));
  const roots = nodes.filter((node) => !node.navigation_parent || !ids.has(node.navigation_parent));
  const selectedNode = nodes.find((node) => node.node_id === selected);
  const degrees = moduleDegrees(nodes, selected);
  return /* @__PURE__ */ jsxs4("div", { className: "pk-view", children: [
    /* @__PURE__ */ jsx4(ViewTitle, { id: "structure", t, subtitle: t("structure.subtitle") }),
    /* @__PURE__ */ jsx4(Section, { title: t("structure.modules"), source: "document", t, hint: t("structure.docHint"), children: /* @__PURE__ */ jsx4(ResourceState, { resource: tree, t, source: "document", empty: !nodes.length, children: /* @__PURE__ */ jsxs4("div", { className: "pk-structure-layout", children: [
      /* @__PURE__ */ jsx4("div", { className: "pk-tree-container", children: /* @__PURE__ */ jsx4("ul", { className: "pk-module-tree", "aria-label": t("structure.navigation"), children: (roots.length ? roots : nodes.slice(0, 1)).map((node) => /* @__PURE__ */ jsx4(ModuleBranch, { node, childrenByParent, expanded, setExpanded, selected, setSelected, t, openDocument }, node.node_id)) }) }),
      /* @__PURE__ */ jsxs4("div", { className: "pk-structure-detail", children: [
        selectedNode && (() => {
          const allDeg = computeAllDegrees(nodes);
          return /* @__PURE__ */ jsx4(
            NodeCard,
            {
              node: selectedNode,
              t,
              openDocument,
              inDeg: allDeg.incoming.get(selectedNode.node_id) ?? 0,
              outDeg: allDeg.outgoing.get(selectedNode.node_id) ?? 0
            }
          );
        })(),
        /* @__PURE__ */ jsxs4("div", { className: "pk-structure-relations", children: [
          /* @__PURE__ */ jsx4("h4", { children: t("structure.relations") }),
          /* @__PURE__ */ jsx4(ModuleGraph, { nodes, selected, setSelected, t }),
          /* @__PURE__ */ jsxs4("p", { className: "pk-edge-legend", children: [
            /* @__PURE__ */ jsx4("span", { className: "pk-edge-swatch pk-dependency-swatch" }),
            t("structure.dependency"),
            /* @__PURE__ */ jsx4("span", { className: "pk-edge-swatch pk-related-swatch" }),
            t("structure.related")
          ] }),
          /* @__PURE__ */ jsx4("p", { className: "pk-tone-legend", children: ["implemented", "limited", "unknown"].map((tone) => /* @__PURE__ */ jsxs4("span", { children: [
            /* @__PURE__ */ jsx4("span", { className: "pk-tone-swatch", "data-tone": tone }),
            t(`structure.tone.${tone}`)
          ] }, tone)) }),
          /* @__PURE__ */ jsxs4("div", { className: "pk-degree-row", children: [
            /* @__PURE__ */ jsx4(SourceTag, { kind: "derived", t }),
            /* @__PURE__ */ jsx4("span", { className: "pk-degree-chip pk-degree-in", "data-tip": t("structure.degreeIncoming"), children: t("structure.inLabel", { n: degrees.incoming }) }),
            /* @__PURE__ */ jsx4("span", { className: "pk-degree-chip pk-degree-out", "data-tip": t("structure.degreeOutgoing"), children: t("structure.outLabel", { n: degrees.outgoing }) }),
            /* @__PURE__ */ jsx4(Info, { text: t("structure.degreeHint") })
          ] })
        ] })
      ] })
    ] }) }) }),
    /* @__PURE__ */ jsx4(Section, { title: t("structure.businessGraph"), t, hint: t("structure.runtimeHint"), children: /* @__PURE__ */ jsx4(TracePanel, { resource: resources.trace, t }) })
  ] });
}

// client/src/views/Requirements.jsx
import React5 from "react";
import { jsx as jsx5, jsxs as jsxs5 } from "react/jsx-runtime";
function coveragePercent(data) {
  const denominator = finiteCount(data?.denominator);
  const covered = finiteCount(data?.covered);
  return denominator && covered != null ? Math.min(100, Math.max(0, covered / denominator * 100)) : null;
}
function Requirements({ resources, t }) {
  const resource = resources.coverage;
  const data = resource?.data || {};
  const requirements = array(data.requirements);
  const percent = coveragePercent(data);
  return /* @__PURE__ */ jsxs5("div", { className: "pk-view", children: [
    /* @__PURE__ */ jsx5(ViewTitle, { id: "requirements", t, subtitle: t("requirements.subtitle") }),
    /* @__PURE__ */ jsx5(Section, { title: t("requirements.coverage"), t, hint: `${t("requirements.scope")} ${t("requirements.denominatorHint")}`, children: /* @__PURE__ */ jsxs5(ResourceState, { resource, t, children: [
      /* @__PURE__ */ jsxs5("div", { className: "pk-stats", children: [
        /* @__PURE__ */ jsx5(Stat, { label: t("requirements.denominator"), value: data.denominator ?? t("common.unknown") }),
        /* @__PURE__ */ jsx5(Stat, { index: 1, label: t("requirements.covered"), value: data.covered ?? t("common.unknown") }),
        /* @__PURE__ */ jsx5(Stat, { index: 2, label: t("requirements.notApplicable"), value: data.not_applicable ?? t("common.unknown") })
      ] }),
      /* @__PURE__ */ jsxs5("div", { className: "pk-coverage-meter", children: [
        /* @__PURE__ */ jsx5("label", { htmlFor: "pk-coverage-progress", children: t("requirements.ratio", { covered: data.covered ?? "\u2014", total: data.denominator ?? "\u2014" }) }),
        percent != null ? /* @__PURE__ */ jsx5("progress", { id: "pk-coverage-progress", value: percent, max: "100", "aria-label": t("requirements.coverage") }) : /* @__PURE__ */ jsx5("p", { className: "pk-note", children: t("requirements.noDenominator") })
      ] }),
      requirements.length ? /* @__PURE__ */ jsx5("div", { className: "pk-table-wrap", children: /* @__PURE__ */ jsxs5("table", { children: [
        /* @__PURE__ */ jsx5("caption", { className: "pk-sr-only", children: t("requirements.coverage") }),
        /* @__PURE__ */ jsx5("thead", { children: /* @__PURE__ */ jsxs5("tr", { children: [
          /* @__PURE__ */ jsx5("th", { children: t("requirements.requirement") }),
          /* @__PURE__ */ jsx5("th", { children: t("requirements.links") }),
          /* @__PURE__ */ jsx5("th", { children: t("requirements.packets") }),
          /* @__PURE__ */ jsx5("th", { children: t("requirements.coverageStatus") }),
          /* @__PURE__ */ jsx5("th", { children: t("requirements.reason") })
        ] }) }),
        /* @__PURE__ */ jsx5("tbody", { children: requirements.map((item) => /* @__PURE__ */ jsxs5("tr", { children: [
          /* @__PURE__ */ jsx5("td", { children: /* @__PURE__ */ jsx5("code", { children: item.object_id }) }),
          /* @__PURE__ */ jsx5("td", { children: item.link_count }),
          /* @__PURE__ */ jsx5("td", { children: /* @__PURE__ */ jsx5("code", { children: textValue(item.linked_packets, t) }) }),
          /* @__PURE__ */ jsx5("td", { children: item.not_applicable ? t("requirements.notApplicable") : textValue(item.coverage, t) }),
          /* @__PURE__ */ jsx5("td", { children: textValue(item.reason, t) })
        ] }, item.object_id)) })
      ] }) }) : /* @__PURE__ */ jsx5("p", { className: "pk-note", children: t("requirements.noRequirements") })
    ] }) }),
    /* @__PURE__ */ jsx5(Section, { title: t("requirements.handoffTrace"), t, hint: t("requirements.chain"), children: /* @__PURE__ */ jsx5(TracePanel, { resource: resources.trace, t }) })
  ] });
}

// client/src/views/Permissions.jsx
import React6, { useEffect, useState as useState3 } from "react";
import { jsx as jsx6, jsxs as jsxs6 } from "react/jsx-runtime";
function candidateOf(compare) {
  const data = compare?.data || {};
  const attempts = array(data.attempts);
  const id = data.selected?.attempt_id;
  const attempt = attempts.find((a) => a.attempt_id === id);
  if (!attempt) return null;
  return { strategy: attempt.strategy_id || shortId(id), verdict: verdictOf(attempt), fit: fitOf(attempt) };
}
function CandidateLine({ candidate, t }) {
  if (!candidate) return null;
  return /* @__PURE__ */ jsxs6("p", { className: "pk-candidate", children: [
    /* @__PURE__ */ jsx6("span", { children: t("permissions.candidate") }),
    /* @__PURE__ */ jsx6("strong", { children: candidate.strategy }),
    /* @__PURE__ */ jsx6(Verdict, { value: candidate.verdict, t, size: "md" }),
    candidate.fit != null && /* @__PURE__ */ jsx6("code", { children: candidate.fit })
  ] });
}
function expirationLabel(expiresAt, now, t) {
  const at = Date.parse(expiresAt);
  if (!Number.isFinite(at)) return t("common.unknown");
  const remaining = Math.max(0, Math.ceil((at - now) / 1e3));
  return remaining === 0 ? t("permissions.expiredTime") : t("permissions.remaining", { minutes: Math.floor(remaining / 60), seconds: String(remaining % 60).padStart(2, "0") });
}
function ApprovalDetails({ approval, t, now, historical = false, index = 0, fresh = false, candidate = null }) {
  const digest = approval.snapshot_digest ? String(approval.snapshot_digest) : null;
  const pending = approval.status === "pending";
  return /* @__PURE__ */ jsxs6("article", { className: `pk-approval-card ${stagger(index)} ${fresh ? "pk-arrived" : ""}`, "data-status": approval.status, children: [
    /* @__PURE__ */ jsxs6("header", { children: [
      /* @__PURE__ */ jsx6("code", { className: "pk-approval-id", children: approval.approval_id }),
      /* @__PURE__ */ jsx6(Badge, { value: approval.status, t })
    ] }),
    pending && /* @__PURE__ */ jsx6(CandidateLine, { candidate, t }),
    digest && /* @__PURE__ */ jsxs6("div", { className: "pk-digest", "data-tip": t("permissions.bindTip"), tabIndex: 0, children: [
      /* @__PURE__ */ jsx6("span", { className: "pk-digest-label", children: t("permissions.digest") }),
      /* @__PURE__ */ jsx6("code", { className: "pk-digest-prefix", children: digest.slice(0, 8) }),
      /* @__PURE__ */ jsx6("code", { className: "pk-digest-rest", children: digest.slice(8, 24) })
    ] }),
    /* @__PURE__ */ jsxs6("dl", { className: "pk-approval-facts", children: [
      /* @__PURE__ */ jsxs6("div", { children: [
        /* @__PURE__ */ jsx6("dt", { children: t("permissions.snapshot") }),
        /* @__PURE__ */ jsx6("dd", { children: /* @__PURE__ */ jsx6("code", { children: approval.snapshot_id ?? "\u2014" }) })
      ] }),
      /* @__PURE__ */ jsxs6("div", { children: [
        /* @__PURE__ */ jsx6("dt", { children: t("permissions.headVersion") }),
        /* @__PURE__ */ jsx6("dd", { children: approval.head_version ?? "\u2014" })
      ] }),
      /* @__PURE__ */ jsxs6("div", { children: [
        /* @__PURE__ */ jsx6("dt", { children: t("permissions.commit") }),
        /* @__PURE__ */ jsxs6("dd", { children: [
          "#",
          approval.commit_seq ?? "\u2014"
        ] })
      ] })
    ] }),
    !historical && pending && Number.isFinite(Date.parse(approval.expires_at)) && /* @__PURE__ */ jsxs6("p", { className: "pk-countdown", children: [
      /* @__PURE__ */ jsx6("span", { children: t("permissions.countdown") }),
      /* @__PURE__ */ jsx6("strong", { children: expirationLabel(approval.expires_at, now, t) })
    ] }),
    pending && /* @__PURE__ */ jsx6("p", { className: "pk-terminal-line", children: t("permissions.terminal") })
  ] });
}
function useClock(active, key) {
  const [now, setNow] = useState3(() => Date.now());
  useEffect(() => {
    if (!active) return void 0;
    const timer = setInterval(() => setNow(Date.now()), 1e3);
    return () => clearInterval(timer);
  }, [active, key]);
  return now;
}
function PermissionNotice({ resource, compare, t, asOfSeq }) {
  const candidate = candidateOf(compare);
  const queue = array(resource?.data?.queue);
  const pending = queue.filter((item) => item.status === "pending");
  const pendingCount = resource?.data?.pending_count ?? pending.length;
  const [dismissed, setDismissed] = useState3("");
  const pendingKey = `${pendingCount}:${pending.map((item) => item.approval_id).join("|")}`;
  const now = useClock(pendingCount > 0 && asOfSeq == null, pendingKey);
  const visible = pendingCount > 0 && dismissed !== pendingKey;
  return visible ? /* @__PURE__ */ jsxs6("aside", { className: "pk-approval-drawer", role: "region", "aria-label": t("permissions.pendingDrawer", { count: pendingCount }), children: [
    /* @__PURE__ */ jsxs6("header", { children: [
      /* @__PURE__ */ jsx6(Verdict, { value: "human", t, size: "md" }),
      /* @__PURE__ */ jsx6("h3", { children: t("permissions.pendingDrawer", { count: pendingCount }) }),
      /* @__PURE__ */ jsx6(Info, { text: t("permissions.humanTip") }),
      /* @__PURE__ */ jsx6("button", { className: "pk-icon-button", type: "button", onClick: () => setDismissed(pendingKey), "aria-label": t("common.close"), children: "\xD7" })
    ] }),
    /* @__PURE__ */ jsx6("div", { className: "pk-approval-row", children: pending.slice(0, 3).map((approval, i) => /* @__PURE__ */ jsx6(ApprovalDetails, { approval, t, now, historical: asOfSeq != null, index: i, candidate }, approval.approval_id)) }),
    pending.length > 3 && /* @__PURE__ */ jsx6("p", { className: "pk-quiet", children: t("permissions.morePending", { count: pending.length - 3 }) })
  ] }) : null;
}
function Permissions({ resources, t, asOfSeq }) {
  const resource = resources.approvals;
  const candidate = candidateOf(resources.compare);
  const queue = array(resource?.data?.queue);
  const now = useClock(asOfSeq == null && queue.some((item) => item.status === "pending"), resource?.data);
  const arrived = useArrivals(queue.map((item) => item.approval_id));
  return /* @__PURE__ */ jsxs6("div", { className: "pk-view", children: [
    /* @__PURE__ */ jsx6(ViewTitle, { id: "permissions", t, subtitle: t("permissions.subtitle") }),
    /* @__PURE__ */ jsx6(Section, { title: t("permissions.queue"), t, hint: t("permissions.humanTip"), children: /* @__PURE__ */ jsxs6(ResourceState, { resource, t, empty: !queue.length, emptyText: t("permissions.noPending"), children: [
      /* @__PURE__ */ jsx6("div", { className: "pk-card-grid", children: queue.map((approval, i) => /* @__PURE__ */ jsx6(ApprovalDetails, { approval, t, now, historical: asOfSeq != null, index: i, fresh: arrived.has(approval.approval_id), candidate }, approval.approval_id)) }),
      asOfSeq != null && /* @__PURE__ */ jsx6("p", { className: "pk-quiet", children: t("permissions.historical") })
    ] }) })
  ] });
}

// client/src/views/Execution.jsx
import React7, { useState as useState4 } from "react";
import { jsx as jsx7, jsxs as jsxs7 } from "react/jsx-runtime";
var costText = (cost, t) => cost == null || cost.state === "unknown" ? t("execution.costUnknown") : textValue(cost.total ?? cost.value ?? cost, t);
function AttemptCard({ attempt, selected, t, index = 0, fresh = false }) {
  const verdict = verdictOf(attempt);
  const fit = fitOf(attempt);
  const reason = reasonOf(attempt);
  const unreported = attempt.cost == null || attempt.cost.state === "unknown";
  return /* @__PURE__ */ jsxs7("article", { className: `pk-attempt-card ${stagger(index)} ${fresh ? "pk-arrived" : ""}`, "data-verdict": verdict, "data-status": attempt.status || "unknown", "data-selected": selected ? "true" : "false", children: [
    /* @__PURE__ */ jsxs7("header", { children: [
      /* @__PURE__ */ jsx7("span", { className: "pk-attempt-strategy", children: attempt.strategy_id || t("common.unknown") }),
      selected && /* @__PURE__ */ jsx7("span", { className: "pk-chip pk-chip-selected", children: t("status.selected") })
    ] }),
    /* @__PURE__ */ jsx7(Verdict, { value: verdict, t, size: "xl", stamp: true }),
    fit != null && /* @__PURE__ */ jsxs7("p", { className: "pk-attempt-fit", children: [
      /* @__PURE__ */ jsx7("i", { children: t("execution.fit") }),
      /* @__PURE__ */ jsx7("strong", { children: fit })
    ] }),
    reason && /* @__PURE__ */ jsx7("p", { className: "pk-attempt-reason", children: reason }),
    /* @__PURE__ */ jsxs7("dl", { className: "pk-attempt-facts", children: [
      /* @__PURE__ */ jsxs7("div", { children: [
        /* @__PURE__ */ jsx7("dt", { children: t("common.status") }),
        /* @__PURE__ */ jsx7("dd", { children: /* @__PURE__ */ jsx7(Badge, { value: attempt.status, t }) })
      ] }),
      /* @__PURE__ */ jsxs7("div", { children: [
        /* @__PURE__ */ jsx7("dt", { children: t("execution.exit") }),
        /* @__PURE__ */ jsx7("dd", { children: /* @__PURE__ */ jsx7("code", { children: attempt.exit_code ?? "\u2014" }) })
      ] }),
      /* @__PURE__ */ jsxs7("div", { children: [
        /* @__PURE__ */ jsx7("dt", { children: t("execution.cost") }),
        /* @__PURE__ */ jsxs7("dd", { children: [
          costText(attempt.cost, t),
          unreported && /* @__PURE__ */ jsx7(Info, { text: t("execution.costTip") })
        ] })
      ] })
    ] }),
    /* @__PURE__ */ jsxs7("footer", { children: [
      /* @__PURE__ */ jsx7("code", { title: attempt.attempt_id, children: shortId(attempt.attempt_id, 10) }),
      /* @__PURE__ */ jsx7("span", { children: attempt.mode }),
      /* @__PURE__ */ jsx7("span", { children: t("execution.revisionsShort", { count: attempt.revision_count ?? "\u2014" }) })
    ] })
  ] });
}
var OPERATION_STATES = ["prepared", "claimed", "applying", "applied", "failed", "unknown"];
function OperationStatus({ resource, t }) {
  const data = resource?.data || {};
  const state = data.status || data.state || data.receipt?.status || "unknown";
  return /* @__PURE__ */ jsxs7(ResourceState, { resource, t, disabledText: t("execution.operationPrompt"), children: [
    /* @__PURE__ */ jsx7(Fields, { t, values: [[t("execution.operationId"), data.operation_id], [t("execution.operationKind"), data.operation_kind]] }),
    /* @__PURE__ */ jsx7("ol", { className: "pk-operation-states", "aria-label": t("execution.operationState"), children: OPERATION_STATES.map((name) => /* @__PURE__ */ jsx7("li", { "data-active": state === name ? "true" : "false", "aria-current": state === name ? "step" : void 0, children: /* @__PURE__ */ jsx7(Badge, { value: name, t }) }, name)) }),
    /* @__PURE__ */ jsxs7("details", { className: "pk-json-details", children: [
      /* @__PURE__ */ jsx7("summary", { children: t("common.details") }),
      /* @__PURE__ */ jsx7("pre", { children: JSON.stringify(data, null, 2) })
    ] })
  ] });
}
function Execution({ resources, t }) {
  const compare = resources.compare;
  const data = compare?.data || {};
  const attempts = array(data.attempts);
  const selectedId = data.selected?.attempt_id;
  const selectedAttempt = attempts.find((attempt) => attempt.attempt_id === selectedId);
  const retained = array(data.failures_retained);
  const [operationId, setOperationId] = useState4("");
  const arrived = useArrivals(attempts.map((attempt) => attempt.attempt_id));
  return /* @__PURE__ */ jsxs7("div", { className: "pk-view", children: [
    /* @__PURE__ */ jsx7(ViewTitle, { id: "execution", t, subtitle: t("execution.subtitle") }),
    /* @__PURE__ */ jsx7(Section, { title: t("execution.attempts"), t, hint: t("execution.runHint"), children: /* @__PURE__ */ jsxs7(ResourceState, { resource: compare, t, empty: !attempts.length, emptyText: t("execution.noAttempts"), children: [
      data.comparability?.comparable === false && /* @__PURE__ */ jsxs7("p", { className: "pk-flag", "data-verdict": "unknown", children: [
        /* @__PURE__ */ jsx7("span", { "aria-hidden": "true", children: "\u25B3" }),
        t("execution.incomparable"),
        ": ",
        textValue(data.comparability.reason, t)
      ] }),
      /* @__PURE__ */ jsx7("div", { className: "pk-compare-grid", "data-count": Math.min(attempts.length, 4), children: attempts.map((attempt, i) => /* @__PURE__ */ jsx7(AttemptCard, { attempt, selected: attempt.attempt_id === selectedId, t, index: i, fresh: arrived.has(attempt.attempt_id) }, attempt.attempt_id)) }),
      data.selected && /* @__PURE__ */ jsxs7("div", { className: "pk-selected", "data-verdict": selectedAttempt ? verdictOf(selectedAttempt) : "open", children: [
        /* @__PURE__ */ jsx7("span", { className: "pk-selected-mark", "aria-hidden": "true", children: "\u2605" }),
        /* @__PURE__ */ jsxs7("div", { children: [
          /* @__PURE__ */ jsx7("h4", { children: t("execution.selection", { strategy: selectedAttempt?.strategy_id ?? shortId(selectedId) }) }),
          /* @__PURE__ */ jsx7("p", { className: "pk-selected-reason", children: textValue(data.selected.reason, t) }),
          /* @__PURE__ */ jsxs7("p", { className: "pk-quiet", children: [
            t("execution.basis"),
            " ",
            /* @__PURE__ */ jsx7("code", { children: data.selected.basis }),
            " \xB7 ",
            /* @__PURE__ */ jsx7("code", { title: selectedId, children: shortId(selectedId, 10) })
          ] })
        ] })
      ] }),
      retained.length > 0 && /* @__PURE__ */ jsxs7("p", { className: "pk-flag", "data-verdict": "unknown", children: [
        /* @__PURE__ */ jsx7("span", { "aria-hidden": "true", children: "?" }),
        t("execution.retained", { count: retained.length }),
        /* @__PURE__ */ jsx7(Info, { text: t("execution.unknownNote") })
      ] })
    ] }) }),
    /* @__PURE__ */ jsxs7("details", { className: "pk-section pk-fold", children: [
      /* @__PURE__ */ jsxs7("summary", { children: [
        /* @__PURE__ */ jsx7("span", { children: t("execution.operation") }),
        /* @__PURE__ */ jsx7("span", { className: "pk-quiet", children: t("execution.operationFold") })
      ] }),
      /* @__PURE__ */ jsxs7("form", { className: "pk-query-form", onSubmit: (event) => {
        event.preventDefault();
        if (operationId.trim()) resources.operation?.refresh?.({ operation_id: operationId.trim() });
      }, children: [
        /* @__PURE__ */ jsxs7("label", { children: [
          t("execution.operationId"),
          /* @__PURE__ */ jsx7("input", { type: "text", value: operationId, maxLength: 256, onChange: (event) => setOperationId(event.target.value), placeholder: t("execution.operationPlaceholder"), required: true })
        ] }),
        /* @__PURE__ */ jsx7("button", { className: "pk-button", type: "submit", children: t("common.query") })
      ] }),
      /* @__PURE__ */ jsx7(OperationStatus, { resource: resources.operation, t })
    ] })
  ] });
}

// client/src/views/Knowledge.jsx
import React8, { useState as useState5 } from "react";
import { jsx as jsx8, jsxs as jsxs8 } from "react/jsx-runtime";
function Knowledge({ t }) {
  const [includeOptional, setIncludeOptional] = useState5(true);
  return /* @__PURE__ */ jsxs8("div", { className: "pk-view pk-knowledge-preview", children: [
    /* @__PURE__ */ jsx8(ViewTitle, { id: "knowledge", t, subtitle: t("knowledge.subtitle") }),
    /* @__PURE__ */ jsxs8("div", { className: "pk-preview-notice", children: [
      /* @__PURE__ */ jsx8(SourceTag, { kind: "preview", t }),
      /* @__PURE__ */ jsx8("p", { children: t("knowledge.notConnected") })
    ] }),
    /* @__PURE__ */ jsxs8("div", { className: "pk-view-grid", children: [
      /* @__PURE__ */ jsx8(Section, { title: t("knowledge.tree"), source: "preview", t, children: /* @__PURE__ */ jsxs8("ul", { className: "pk-knowledge-tree", children: [
        /* @__PURE__ */ jsx8("li", { children: /* @__PURE__ */ jsxs8("details", { open: true, children: [
          /* @__PURE__ */ jsx8("summary", { children: t("knowledge.project") }),
          /* @__PURE__ */ jsxs8("ul", { children: [
            /* @__PURE__ */ jsx8("li", { children: t("knowledge.contracts") }),
            /* @__PURE__ */ jsx8("li", { children: t("knowledge.decisions") }),
            /* @__PURE__ */ jsx8("li", { children: t("knowledge.evidence") })
          ] })
        ] }) }),
        /* @__PURE__ */ jsx8("li", { children: /* @__PURE__ */ jsxs8("details", { open: true, children: [
          /* @__PURE__ */ jsx8("summary", { children: t("knowledge.profile") }),
          /* @__PURE__ */ jsxs8("ul", { children: [
            /* @__PURE__ */ jsx8("li", { children: t("knowledge.preferences") }),
            /* @__PURE__ */ jsx8("li", { children: t("knowledge.feedback") })
          ] })
        ] }) })
      ] }) }),
      /* @__PURE__ */ jsxs8(Section, { title: t("knowledge.budget"), source: "preview", t, hint: t("knowledge.budgetHint"), children: [
        /* @__PURE__ */ jsxs8("div", { className: "pk-budget-card", "data-priority": "mandatory", children: [
          /* @__PURE__ */ jsx8("strong", { children: t("knowledge.mandatory") }),
          /* @__PURE__ */ jsx8("p", { children: t("knowledge.mandatoryDetail") }),
          /* @__PURE__ */ jsx8("span", { className: "pk-badge", children: t("knowledge.retained") })
        ] }),
        /* @__PURE__ */ jsxs8("div", { className: "pk-budget-card", "data-priority": "optional", children: [
          /* @__PURE__ */ jsxs8("label", { className: "pk-check-label", children: [
            /* @__PURE__ */ jsx8("input", { type: "checkbox", checked: includeOptional, onChange: (event) => setIncludeOptional(event.target.checked) }),
            t("knowledge.optional")
          ] }),
          /* @__PURE__ */ jsx8("p", { children: t("knowledge.optionalDetail") }),
          /* @__PURE__ */ jsx8("p", { className: "pk-note", children: t(includeOptional ? "knowledge.optionalIncluded" : "knowledge.optionalExcluded") })
        ] })
      ] })
    ] }),
    /* @__PURE__ */ jsx8(Section, { title: t("knowledge.provenance"), source: "preview", t, children: /* @__PURE__ */ jsxs8("div", { className: "pk-knowledge-source", children: [
      /* @__PURE__ */ jsx8("code", { children: "docs/records/user-learning-profile.md" }),
      /* @__PURE__ */ jsx8("p", { children: t("knowledge.sourceLimit") }),
      /* @__PURE__ */ jsx8("blockquote", { children: t("knowledge.sampleSummary") }),
      /* @__PURE__ */ jsx8("p", { className: "pk-note", children: t("knowledge.descriptive") })
    ] }) })
  ] });
}

// client/src/views/Errors.jsx
import React9 from "react";
import { jsx as jsx9, jsxs as jsxs9 } from "react/jsx-runtime";
function BarChart({ counts, t, label }) {
  const entries2 = Object.entries(counts);
  const largest = Math.max(1, ...entries2.map(([, value]) => value));
  const height = entries2.length * 46 + 36;
  return entries2.length ? /* @__PURE__ */ jsx9("div", { className: "pk-chart-scroll", children: /* @__PURE__ */ jsxs9("svg", { className: "pk-bar-chart", viewBox: `0 0 660 ${height}`, width: "660", height, role: "img", "aria-label": label, children: [
    /* @__PURE__ */ jsx9("title", { children: label }),
    entries2.map(([name, value], i) => /* @__PURE__ */ jsxs9("g", { transform: `translate(0,${i * 46 + 25})`, "data-status": name, children: [
      /* @__PURE__ */ jsx9("text", { x: "0", y: "0", children: name.length > 27 ? `${name.slice(0, 26)}\u2026` : name }),
      /* @__PURE__ */ jsx9("rect", { x: "240", y: "-15", width: Math.max(1, value / largest * 340), height: "23", rx: "2" }),
      /* @__PURE__ */ jsx9("text", { x: 252 + value / largest * 340, y: "1", children: value }),
      /* @__PURE__ */ jsx9("title", { children: `${name}: ${value}` })
    ] }, name))
  ] }) }) : /* @__PURE__ */ jsx9("p", { className: "pk-note", children: t("errors.noObservations") });
}
function FailureSeries({ events, t }) {
  const series = timelineFailureSeries(events);
  if (!series.length) return /* @__PURE__ */ jsx9("p", { className: "pk-note", children: t("errors.noExplicitEvents") });
  const width = 680;
  const height = 210;
  const maximum = Math.max(1, ...series.map((item) => Math.max(item.failed, item.unknown)));
  const x = (i) => series.length === 1 ? 335 : 45 + i / (series.length - 1) * 590;
  const y = (value) => 160 - value / maximum * 125;
  return /* @__PURE__ */ jsxs9("div", { className: "pk-chart-scroll", children: [
    /* @__PURE__ */ jsxs9("svg", { className: "pk-series-chart", viewBox: `0 0 ${width} ${height}`, width, height, role: "img", "aria-label": t("errors.series"), children: [
      /* @__PURE__ */ jsx9("title", { children: t("errors.series") }),
      /* @__PURE__ */ jsx9("path", { className: "pk-chart-axis", d: "M45,25 V160 H635" }),
      ["failed", "unknown"].map((kind) => /* @__PURE__ */ jsxs9("g", { "data-kind": kind, children: [
        /* @__PURE__ */ jsx9("polyline", { points: series.map((item, i) => `${x(i)},${y(item[kind])}`).join(" ") }),
        series.map((item, i) => /* @__PURE__ */ jsx9("circle", { cx: x(i), cy: y(item[kind]), r: "4", children: /* @__PURE__ */ jsx9("title", { children: `${item.seq} \xB7 ${t(`status.${kind}`)}: ${item[kind]}` }) }, item.seq))
      ] }, kind)),
      /* @__PURE__ */ jsx9("text", { x: "45", y: "185", children: series[0].seq }),
      /* @__PURE__ */ jsx9("text", { x: "610", y: "185", children: series.at(-1).seq }),
      /* @__PURE__ */ jsx9("text", { x: "5", y: "35", children: maximum }),
      /* @__PURE__ */ jsx9("text", { x: "335", y: "207", textAnchor: "middle", children: t("errors.sequence") })
    ] }),
    /* @__PURE__ */ jsxs9("div", { className: "pk-chart-legend", children: [
      /* @__PURE__ */ jsx9("span", { className: "pk-legend-failed", children: t("status.failed") }),
      /* @__PURE__ */ jsx9("span", { className: "pk-legend-unknown", children: t("status.unknown") })
    ] })
  ] });
}
function Errors({ resources, t }) {
  const compare = resources.compare;
  const overview = resources.overview;
  const timeline = resources.timeline;
  const events = array(timeline?.data?.events);
  const tip = t("errors.derivedNote");
  return /* @__PURE__ */ jsxs9("div", { className: "pk-view", children: [
    /* @__PURE__ */ jsx9(ViewTitle, { id: "errors", t, subtitle: t("errors.subtitle") }),
    /* @__PURE__ */ jsxs9("div", { className: "pk-view-grid", children: [
      /* @__PURE__ */ jsx9(Section, { title: t("errors.attemptStates"), source: "derived", t, hint: tip, children: /* @__PURE__ */ jsx9(ResourceState, { resource: compare, t, children: /* @__PURE__ */ jsx9(BarChart, { counts: statusDistribution(compare?.data), t, label: t("errors.attemptStates") }) }) }),
      /* @__PURE__ */ jsx9(Section, { title: t("errors.eventTypes"), source: "derived", t, hint: tip, children: /* @__PURE__ */ jsx9(ResourceState, { resource: timeline, t, children: /* @__PURE__ */ jsx9(BarChart, { counts: tally(events, (event) => event.event_type || event.kind), t, label: t("errors.eventTypes") }) }) }),
      /* @__PURE__ */ jsx9(Section, { title: t("errors.retained"), source: "derived", t, hint: tip, children: /* @__PURE__ */ jsxs9(ResourceState, { resource: compare, t, children: [
        /* @__PURE__ */ jsx9(Stat, { label: t("errors.retainedCount"), value: array(compare?.data?.failures_retained).length }),
        /* @__PURE__ */ jsx9(DataList, { items: compare?.data?.failures_retained, t })
      ] }) }),
      /* @__PURE__ */ jsx9(Section, { title: t("errors.blockers"), source: "derived", t, hint: tip, children: /* @__PURE__ */ jsxs9(ResourceState, { resource: overview, t, children: [
        /* @__PURE__ */ jsx9(Stat, { label: t("errors.blockerCount"), value: array(overview?.data?.blockers).length }),
        /* @__PURE__ */ jsx9(DataList, { items: overview?.data?.blockers, t })
      ] }) })
    ] }),
    /* @__PURE__ */ jsx9(Section, { title: t("errors.series"), source: "derived", t, hint: `${tip} ${t("errors.seriesTip")}`, children: /* @__PURE__ */ jsx9(ResourceState, { resource: timeline, t, children: /* @__PURE__ */ jsx9(FailureSeries, { events, t }) }) })
  ] });
}

// client/src/views/Skills.jsx
import React10, { useState as useState6 } from "react";
import { jsx as jsx10, jsxs as jsxs10 } from "react/jsx-runtime";
var SCORE_DIMENSIONS = ["correctness", "applicability", "reuse_benefit", "maintainability"];
function AssessmentPreview({ t }) {
  const [scores, setScores] = useState6(() => Object.fromEntries(SCORE_DIMENSIONS.map((dimension) => [dimension, "null"])));
  return /* @__PURE__ */ jsxs10("div", { className: "pk-assessment-preview", children: [
    /* @__PURE__ */ jsx10("p", { className: "pk-note", children: t("skills.scoreHint") }),
    /* @__PURE__ */ jsxs10("form", { className: "pk-preview-form", onSubmit: (event) => event.preventDefault(), children: [
      /* @__PURE__ */ jsxs10("label", { children: [
        t("skills.newSkill"),
        /* @__PURE__ */ jsx10("input", { placeholder: t("skills.namePlaceholder"), maxLength: 128 })
      ] }),
      /* @__PURE__ */ jsxs10("label", { children: [
        t("skills.version"),
        /* @__PURE__ */ jsx10("input", { placeholder: "0.1.0", maxLength: 64 })
      ] }),
      /* @__PURE__ */ jsxs10("label", { className: "pk-form-wide", children: [
        t("skills.scope"),
        /* @__PURE__ */ jsx10("textarea", { placeholder: t("skills.scopePlaceholder"), rows: "2", maxLength: 2e3 })
      ] }),
      SCORE_DIMENSIONS.map((dimension) => /* @__PURE__ */ jsxs10("label", { children: [
        t(`score.${dimension}`),
        /* @__PURE__ */ jsx10("select", { value: scores[dimension], onChange: (event) => setScores({ ...scores, [dimension]: event.target.value }), children: ["null", "0", "1", "2"].map((score) => /* @__PURE__ */ jsx10("option", { value: score, children: score === "null" ? t("skills.unassessed") : t(`score.value${score}`) }, score)) })
      ] }, dimension))
    ] }),
    /* @__PURE__ */ jsx10("p", { className: "pk-note", children: t("skills.localOnly") })
  ] });
}
function Skills({ resources, t }) {
  const resource = resources.skills;
  const skills = array(resource?.data?.skills);
  return /* @__PURE__ */ jsxs10("div", { className: "pk-view", children: [
    /* @__PURE__ */ jsx10(ViewTitle, { id: "skills", t, subtitle: t("skills.subtitle") }),
    /* @__PURE__ */ jsx10(Section, { title: t("skills.registry"), source: "document", t, hint: t("skills.registryHint"), children: /* @__PURE__ */ jsx10(ResourceState, { resource, t, source: "document", empty: !skills.length, children: /* @__PURE__ */ jsx10("div", { className: "pk-skill-list", children: skills.map((skill, i) => /* @__PURE__ */ jsxs10("article", { className: `pk-skill-card ${stagger(i)}`, children: [
      /* @__PURE__ */ jsxs10("header", { children: [
        /* @__PURE__ */ jsx10("h4", { children: /* @__PURE__ */ jsx10("code", { children: skill.skill_id }) }),
        /* @__PURE__ */ jsxs10("span", { children: [
          t("skills.currentVersion"),
          ": ",
          /* @__PURE__ */ jsx10("code", { children: skill.current_version })
        ] })
      ] }),
      /* @__PURE__ */ jsx10("p", { children: /* @__PURE__ */ jsx10("code", { children: skill.path }) }),
      array(skill.versions).map((version) => /* @__PURE__ */ jsxs10("details", { className: "pk-skill-version", open: version.version === skill.current_version, children: [
        /* @__PURE__ */ jsxs10("summary", { children: [
          /* @__PURE__ */ jsx10("code", { children: version.version }),
          /* @__PURE__ */ jsx10(Badge, { value: version.status, t }),
          /* @__PURE__ */ jsx10(Badge, { value: version.validation_status, t })
        ] }),
        /* @__PURE__ */ jsx10(Fields, { t, values: [[t("skills.sourceRevision"), version.source_revision]] }),
        ["applies_to", "prerequisites", "exclusions"].map((key) => /* @__PURE__ */ jsxs10("div", { className: "pk-scope-group", children: [
          /* @__PURE__ */ jsx10("h5", { children: t(`skills.${key}`) }),
          /* @__PURE__ */ jsx10(DataList, { items: version.scope?.[key], t })
        ] }, key)),
        /* @__PURE__ */ jsx10("h5", { children: t("skills.reviewRefs") }),
        /* @__PURE__ */ jsx10(DataList, { items: version.review_refs, t }),
        /* @__PURE__ */ jsx10("h5", { children: t("skills.evidenceRefs") }),
        /* @__PURE__ */ jsx10(DataList, { items: version.evidence_refs, t })
      ] }, version.version)),
      /* @__PURE__ */ jsx10("h5", { children: t("skills.recordedScores") }),
      /* @__PURE__ */ jsx10(Fields, { t, values: SCORE_DIMENSIONS.map((dimension) => [t(`score.${dimension}`), t("skills.unassessed")]) }),
      /* @__PURE__ */ jsx10("p", { className: "pk-note", children: t("skills.noRecordedScores") })
    ] }, skill.skill_id)) }) }) }),
    /* @__PURE__ */ jsx10(Section, { title: t("skills.formPreview"), source: "preview", t, children: /* @__PURE__ */ jsx10(AssessmentPreview, { t }) })
  ] });
}

// client/src/views/Environment.jsx
import React11 from "react";
import { jsx as jsx11, jsxs as jsxs11 } from "react/jsx-runtime";
var ENVIRONMENT_BUCKETS = ["satisfied", "missing", "unknown", "too_old", "not_checked"];
function environmentBuckets(data) {
  return Object.fromEntries(ENVIRONMENT_BUCKETS.map((state) => [state, Array.isArray(data?.[state]) ? data[state] : array(data?.facts).filter((fact) => fact.state === state)]));
}
function Environment({ resources, t }) {
  const resource = resources.environment;
  const data = resource?.data || {};
  const buckets = environmentBuckets(data);
  return /* @__PURE__ */ jsxs11("div", { className: "pk-view", children: [
    /* @__PURE__ */ jsx11(ViewTitle, { id: "environment", t, subtitle: t("environment.subtitle") }),
    /* @__PURE__ */ jsxs11(Section, { title: t("environment.report"), t, children: [
      /* @__PURE__ */ jsxs11(ResourceState, { resource, t, empty: data.data_state === "no_data", emptyText: t("environment.noProbe"), children: [
        data.data_state === "source_failed" && /* @__PURE__ */ jsx11(EmptyState, { t, kind: "error", message: t("environment.sourceFailed") }),
        /* @__PURE__ */ jsx11(Fields, { t, values: [[t("environment.checkedAt"), data.checked_at], [t("environment.freshness"), data.freshness_state], [t("environment.snapshot"), data.snapshot], [t("environment.dataState"), data.data_state]] }),
        /* @__PURE__ */ jsx11("div", { className: "pk-env-buckets", children: ENVIRONMENT_BUCKETS.map((state) => /* @__PURE__ */ jsxs11("section", { className: "pk-env-bucket", "data-state": state, children: [
          /* @__PURE__ */ jsxs11("header", { children: [
            /* @__PURE__ */ jsx11("h4", { children: /* @__PURE__ */ jsx11(Badge, { value: state, t }) }),
            /* @__PURE__ */ jsx11("span", { className: "pk-env-count", children: buckets[state].length })
          ] }),
          buckets[state].length ? /* @__PURE__ */ jsx11("div", { className: "pk-table-wrap", children: /* @__PURE__ */ jsxs11("table", { children: [
            /* @__PURE__ */ jsx11("caption", { className: "pk-sr-only", children: t(`status.${state}`) }),
            /* @__PURE__ */ jsx11("thead", { children: /* @__PURE__ */ jsxs11("tr", { children: [
              /* @__PURE__ */ jsx11("th", { children: t("environment.requirement") }),
              /* @__PURE__ */ jsx11("th", { children: t("environment.requiredVersion") }),
              /* @__PURE__ */ jsx11("th", { children: t("environment.installedVersion") }),
              /* @__PURE__ */ jsx11("th", { children: t("environment.path") })
            ] }) }),
            /* @__PURE__ */ jsx11("tbody", { children: buckets[state].map((fact, i) => /* @__PURE__ */ jsxs11("tr", { children: [
              /* @__PURE__ */ jsxs11("td", { children: [
                /* @__PURE__ */ jsx11("code", { children: textValue(fact.requirement, t) }),
                /* @__PURE__ */ jsxs11("details", { children: [
                  /* @__PURE__ */ jsx11("summary", { children: t("common.details") }),
                  /* @__PURE__ */ jsx11("pre", { children: JSON.stringify(fact.detail, null, 2) })
                ] })
              ] }),
              /* @__PURE__ */ jsx11("td", { children: textValue(fact.required_version, t) }),
              /* @__PURE__ */ jsx11("td", { children: textValue(fact.installed_version, t) }),
              /* @__PURE__ */ jsx11("td", { children: /* @__PURE__ */ jsx11("code", { children: textValue(fact.path, t) }) })
            ] }, `${textValue(fact.requirement, t)}:${i}`)) })
          ] }) }) : /* @__PURE__ */ jsx11("p", { className: "pk-note", children: t("environment.bucketEmpty") })
        ] }, state)) })
      ] }),
      /* @__PURE__ */ jsx11("p", { className: "pk-note", children: t("environment.readOnlyHint") })
    ] })
  ] });
}

// client/src/views/Versions.jsx
import React12, { useState as useState7 } from "react";
import { jsx as jsx12, jsxs as jsxs12 } from "react/jsx-runtime";
function sortTimeline(events) {
  return [...array(events)].sort((a, b) => {
    try {
      const left = BigInt(a.commit_seq);
      const right = BigInt(b.commit_seq);
      return left === right ? 0 : left > right ? -1 : 1;
    } catch {
      return 0;
    }
  });
}
function Versions({ resources, t, asOfSeq, setAsOfSeq, maxSeq }) {
  const resource = resources.timeline;
  const events = sortTimeline(resource?.data?.events);
  const [filter, setFilter] = useState7("");
  const maxNumber = Number(maxSeq);
  const validMax = Number.isSafeInteger(maxNumber) && maxNumber >= 0;
  const [draftSeq, setDraftSeq] = useState7(null);
  const selectedSeq = draftSeq ?? (asOfSeq == null ? maxSeq || "0" : asOfSeq);
  const types = [...new Set(events.map((event) => event.object_type).filter(Boolean))].sort();
  const pageToken = resource?.meta?.next_page_token ?? resource?.data?.next_page_token;
  const rows = events.filter((event) => !filter || event.object_type === filter);
  const applyHistory = () => {
    if (validMax) {
      setAsOfSeq?.(String(selectedSeq));
      setDraftSeq(null);
    }
  };
  return /* @__PURE__ */ jsxs12("div", { className: "pk-view", children: [
    /* @__PURE__ */ jsx12(ViewTitle, { id: "versions", t, subtitle: t("versions.subtitle") }),
    /* @__PURE__ */ jsxs12(Section, { title: t("versions.watermark"), t, hint: t("versions.watermarkHint"), children: [
      /* @__PURE__ */ jsxs12("div", { className: "pk-history-controls", children: [
        /* @__PURE__ */ jsxs12("label", { htmlFor: "pk-history-slider", children: [
          t("shell.asOf"),
          ": ",
          /* @__PURE__ */ jsx12("output", { htmlFor: "pk-history-slider", children: selectedSeq })
        ] }),
        /* @__PURE__ */ jsx12("input", { id: "pk-history-slider", type: "range", min: "0", max: validMax ? maxNumber : 0, value: validMax ? Math.min(maxNumber, Math.max(0, Number(selectedSeq))) : 0, disabled: !validMax, onChange: (event) => setDraftSeq(event.target.value) }),
        /* @__PURE__ */ jsxs12("div", { className: "pk-control-actions", children: [
          /* @__PURE__ */ jsx12("button", { className: "pk-button", type: "button", disabled: !validMax, onClick: applyHistory, children: t("versions.viewHistory") }),
          /* @__PURE__ */ jsx12("button", { className: "pk-button pk-button-secondary", type: "button", onClick: () => {
            setDraftSeq(null);
            setAsOfSeq?.(null);
          }, children: t("versions.returnCurrent") })
        ] })
      ] }),
      asOfSeq != null && /* @__PURE__ */ jsx12("p", { className: "pk-note pk-note-warn", children: t("shell.history", { seq: asOfSeq }) }),
      !validMax && /* @__PURE__ */ jsx12("p", { className: "pk-note", children: t("versions.noHead") })
    ] }),
    /* @__PURE__ */ jsxs12(Section, { title: t("versions.timeline"), t, children: [
      /* @__PURE__ */ jsxs12("div", { className: "pk-timeline-tools", children: [
        /* @__PURE__ */ jsxs12("label", { children: [
          t("versions.objectFilter"),
          /* @__PURE__ */ jsxs12("select", { value: filter, onChange: (event) => setFilter(event.target.value), children: [
            /* @__PURE__ */ jsx12("option", { value: "", children: t("common.all") }),
            types.map((type) => /* @__PURE__ */ jsx12("option", { value: type, children: type }, type))
          ] })
        ] }),
        /* @__PURE__ */ jsx12("button", { className: "pk-button pk-button-secondary", type: "button", onClick: () => resource?.refresh?.({ page_token: void 0 }), children: t("versions.firstPage") })
      ] }),
      /* @__PURE__ */ jsx12(ResourceState, { resource, t, empty: !rows.length, emptyText: filter ? t("versions.noMatchingEvents") : t("versions.noEvents"), children: /* @__PURE__ */ jsx12("ol", { className: "pk-timeline", children: rows.map((event, i) => /* @__PURE__ */ jsxs12("li", { className: stagger(i), "data-kind": event.kind, children: [
        /* @__PURE__ */ jsx12("span", { className: "pk-timeline-symbol", "aria-hidden": "true", children: event.kind === "revision" ? "\u25C7" : event.kind === "head" ? "\u25C6" : "\u2022" }),
        /* @__PURE__ */ jsxs12("article", { children: [
          /* @__PURE__ */ jsxs12("header", { children: [
            /* @__PURE__ */ jsxs12("strong", { children: [
              "#",
              event.commit_seq
            ] }),
            /* @__PURE__ */ jsx12("span", { className: "pk-badge", children: ["revision", "head", "event"].includes(event.kind) ? t(`versions.kind.${event.kind}`) : event.kind })
          ] }),
          /* @__PURE__ */ jsx12(Fields, { t, values: [[t("trace.object_type"), event.object_type], [t("trace.object_id"), event.object_id], [t("trace.revision_id"), event.revision_id], [t("versions.eventType"), event.event_type]] }),
          /* @__PURE__ */ jsxs12("details", { className: "pk-json-details", children: [
            /* @__PURE__ */ jsx12("summary", { children: t("common.details") }),
            /* @__PURE__ */ jsx12("pre", { children: JSON.stringify(event, null, 2) })
          ] })
        ] })
      ] }, JSON.stringify([event.commit_seq, event.kind, event.object_type, event.object_id, event.revision_id, event.pointer_name, event.head_version, event.event_type, event.event_index, i]))) }) }),
      /* @__PURE__ */ jsxs12("footer", { className: "pk-page-tools", children: [
        /* @__PURE__ */ jsx12("p", { className: "pk-note", children: t("versions.pageCount", { count: rows.length }) }),
        /* @__PURE__ */ jsx12("button", { className: "pk-button", type: "button", disabled: !pageToken || resource?.phase === "loading", onClick: () => resource?.refresh?.({ page_token: pageToken }), children: t("versions.nextPage") })
      ] }),
      /* @__PURE__ */ jsx12("p", { className: "pk-note", children: t("versions.filterScope") })
    ] }),
    /* @__PURE__ */ jsx12("p", { className: "pk-note", children: t("versions.rulesHint") })
  ] });
}

// client/src/views/WorkspaceProject.jsx
import React13, { useState as useState8 } from "react";
import { jsx as jsx13, jsxs as jsxs13 } from "react/jsx-runtime";
function WorkspaceProject({ resources, t }) {
  const [showImport, setShowImport] = useState8(false);
  const [importSource, setImportSource] = useState8("");
  const [importName, setImportName] = useState8("");
  const currentWorkspace = { id: "example-ws-1", name: "[\u793A\u4F8B] kernel-demo", path: "/path/to/kernel_next" };
  const workspaces = [
    currentWorkspace,
    { id: "example-ws-2", name: "[\u793A\u4F8B] other-workspace", path: "/path/to/other" }
  ];
  const currentProject = { id: "example-proj-1", name: "[\u793A\u4F8B] project-kernel", workspace: "example-ws-1", hasStore: true, lastOpened: "2026-10-14T10:30:00Z" };
  const projects = [
    currentProject,
    { id: "example-proj-2", name: "[\u793A\u4F8B] agh-integration", workspace: "example-ws-1", hasStore: true, lastOpened: "2026-10-13T16:00:00Z" },
    { id: "example-proj-3", name: "[\u793A\u4F8B] demo-project", workspace: "example-ws-2", hasStore: false, lastOpened: null }
  ];
  return /* @__PURE__ */ jsxs13("div", { className: "pk-view", children: [
    /* @__PURE__ */ jsx13(ViewTitle, { id: "workspace", t, subtitle: t("workspace.subtitle") }),
    /* @__PURE__ */ jsxs13(Section, { title: t("workspace.current"), source: "preview", t, children: [
      /* @__PURE__ */ jsxs13("div", { className: "pk-preview-notice", children: [
        /* @__PURE__ */ jsx13(SourceTag, { kind: "preview", t }),
        /* @__PURE__ */ jsx13("p", { children: t("workspace.previewNote") })
      ] }),
      /* @__PURE__ */ jsxs13("article", { className: "pk-workspace-card pk-current", children: [
        /* @__PURE__ */ jsxs13("header", { children: [
          /* @__PURE__ */ jsx13("h3", { children: currentWorkspace.name }),
          /* @__PURE__ */ jsx13(Badge, { value: "selected", t })
        ] }),
        /* @__PURE__ */ jsxs13("dl", { className: "pk-fields", children: [
          /* @__PURE__ */ jsxs13("div", { children: [
            /* @__PURE__ */ jsx13("dt", { children: t("workspace.path") }),
            /* @__PURE__ */ jsx13("dd", { children: /* @__PURE__ */ jsx13("code", { children: currentWorkspace.path }) })
          ] }),
          /* @__PURE__ */ jsxs13("div", { children: [
            /* @__PURE__ */ jsx13("dt", { children: t("workspace.projectCount") }),
            /* @__PURE__ */ jsx13("dd", { children: projects.filter((p) => p.workspace === currentWorkspace.id).length })
          ] })
        ] })
      ] }),
      /* @__PURE__ */ jsx13("h4", { children: t("workspace.currentProject") }),
      /* @__PURE__ */ jsxs13("article", { className: "pk-project-card pk-current", children: [
        /* @__PURE__ */ jsxs13("header", { children: [
          /* @__PURE__ */ jsx13("h4", { children: /* @__PURE__ */ jsx13("code", { children: currentProject.name }) }),
          /* @__PURE__ */ jsx13(Badge, { value: currentProject.hasStore ? "ok" : "missing", t })
        ] }),
        /* @__PURE__ */ jsxs13("dl", { className: "pk-node-facts", children: [
          /* @__PURE__ */ jsxs13("div", { children: [
            /* @__PURE__ */ jsx13("dt", { children: t("workspace.projectId") }),
            /* @__PURE__ */ jsx13("dd", { children: /* @__PURE__ */ jsx13("code", { children: currentProject.id }) })
          ] }),
          /* @__PURE__ */ jsxs13("div", { children: [
            /* @__PURE__ */ jsx13("dt", { children: t("workspace.hasStore") }),
            /* @__PURE__ */ jsx13("dd", { children: currentProject.hasStore ? t("common.yes") : t("common.no") })
          ] }),
          currentProject.lastOpened && /* @__PURE__ */ jsxs13("div", { children: [
            /* @__PURE__ */ jsx13("dt", { children: t("workspace.lastOpened") }),
            /* @__PURE__ */ jsx13("dd", { children: currentProject.lastOpened.split("T")[0] })
          ] })
        ] })
      ] })
    ] }),
    /* @__PURE__ */ jsxs13(Section, { title: t("workspace.allWorkspaces"), source: "preview", t, children: [
      /* @__PURE__ */ jsx13("div", { className: "pk-workspace-list", children: workspaces.map((ws) => /* @__PURE__ */ jsxs13("article", { className: `pk-workspace-card ${ws.id === currentWorkspace.id ? "pk-current" : ""}`, children: [
        /* @__PURE__ */ jsxs13("header", { children: [
          /* @__PURE__ */ jsx13("h3", { children: ws.name }),
          ws.id === currentWorkspace.id && /* @__PURE__ */ jsx13(Badge, { value: "selected", t })
        ] }),
        /* @__PURE__ */ jsx13("p", { className: "pk-path", children: /* @__PURE__ */ jsx13("code", { children: ws.path }) }),
        /* @__PURE__ */ jsxs13("div", { className: "pk-project-count", children: [
          projects.filter((p) => p.workspace === ws.id).length,
          " ",
          t("workspace.projects")
        ] }),
        ws.id !== currentWorkspace.id && /* @__PURE__ */ jsx13("button", { className: "pk-button", disabled: true, children: t("workspace.switchTo") })
      ] }, ws.id)) }),
      /* @__PURE__ */ jsx13("button", { className: "pk-button", disabled: true, children: t("workspace.create") })
    ] }),
    /* @__PURE__ */ jsx13(Section, { title: t("workspace.allProjects"), source: "preview", t, children: /* @__PURE__ */ jsx13("div", { className: "pk-project-grid", children: projects.map((proj) => /* @__PURE__ */ jsxs13("article", { className: `pk-project-card ${proj.id === currentProject.id ? "pk-current" : ""}`, children: [
      /* @__PURE__ */ jsxs13("header", { children: [
        /* @__PURE__ */ jsx13("h4", { children: /* @__PURE__ */ jsx13("code", { children: proj.name }) }),
        /* @__PURE__ */ jsx13(Badge, { value: proj.hasStore ? proj.id === currentProject.id ? "selected" : "ok" : "missing", t })
      ] }),
      /* @__PURE__ */ jsxs13("dl", { className: "pk-node-facts", children: [
        /* @__PURE__ */ jsxs13("div", { children: [
          /* @__PURE__ */ jsx13("dt", { children: t("workspace.workspace") }),
          /* @__PURE__ */ jsx13("dd", { children: workspaces.find((w) => w.id === proj.workspace)?.name })
        ] }),
        proj.lastOpened && /* @__PURE__ */ jsxs13("div", { children: [
          /* @__PURE__ */ jsx13("dt", { children: t("workspace.lastOpened") }),
          /* @__PURE__ */ jsx13("dd", { children: proj.lastOpened.split("T")[0] })
        ] })
      ] }),
      proj.id !== currentProject.id && /* @__PURE__ */ jsx13("button", { className: "pk-button", disabled: true, children: t("workspace.open") })
    ] }, proj.id)) }) }),
    /* @__PURE__ */ jsx13(Section, { title: t("workspace.import"), source: "preview", t, children: !showImport ? /* @__PURE__ */ jsx13("button", { className: "pk-button", onClick: () => setShowImport(true), children: t("workspace.importProject") }) : /* @__PURE__ */ jsxs13("form", { className: "pk-import-form", onSubmit: (e) => e.preventDefault(), children: [
      /* @__PURE__ */ jsxs13("label", { children: [
        t("workspace.importSource"),
        /* @__PURE__ */ jsx13("input", { value: importSource, placeholder: t("workspace.sourcePlaceholder"), onChange: (e) => setImportSource(e.target.value) })
      ] }),
      /* @__PURE__ */ jsxs13("label", { children: [
        t("workspace.importName"),
        /* @__PURE__ */ jsx13("input", { value: importName, placeholder: t("workspace.namePlaceholder"), onChange: (e) => setImportName(e.target.value) })
      ] }),
      /* @__PURE__ */ jsxs13("div", { className: "pk-control-actions", children: [
        /* @__PURE__ */ jsx13("button", { className: "pk-button", type: "submit", disabled: true, children: t("workspace.importAction") }),
        /* @__PURE__ */ jsx13("button", { className: "pk-text-button", type: "button", onClick: () => setShowImport(false), children: t("common.close") })
      ] })
    ] }) }),
    /* @__PURE__ */ jsxs13(Section, { title: t("workspace.implementation"), source: "preview", t, children: [
      /* @__PURE__ */ jsxs13("ul", { className: "pk-data-list", children: [
        /* @__PURE__ */ jsxs13("li", { children: [
          /* @__PURE__ */ jsx13("code", { children: "workspace.list" }),
          " \u2014 ",
          t("workspace.cmdList")
        ] }),
        /* @__PURE__ */ jsxs13("li", { children: [
          /* @__PURE__ */ jsx13("code", { children: "workspace.create" }),
          " \u2014 ",
          t("workspace.cmdCreate")
        ] }),
        /* @__PURE__ */ jsxs13("li", { children: [
          /* @__PURE__ */ jsx13("code", { children: "project.import" }),
          " \u2014 ",
          t("workspace.cmdImport")
        ] }),
        /* @__PURE__ */ jsxs13("li", { children: [
          /* @__PURE__ */ jsx13("code", { children: "project.select" }),
          " \u2014 ",
          t("workspace.cmdSelect")
        ] })
      ] }),
      /* @__PURE__ */ jsx13("p", { className: "pk-note", children: t("workspace.implementationNote") })
    ] })
  ] });
}

// client/src/views/Documents.jsx
import React15, { useMemo as useMemo2, useState as useState9 } from "react";

// client/src/parts/Markdown.jsx
import React14 from "react";
import { jsx as jsx14, jsxs as jsxs14 } from "react/jsx-runtime";
function inline(text, openDocument, keyBase) {
  const parts = [];
  const pattern = /(`[^`]+`)|\[([^\]]+)\]\(([^)\s]+)\)|\*\*([^*]+)\*\*/g;
  let last = 0;
  let match;
  let i = 0;
  while (match = pattern.exec(text)) {
    if (match.index > last) parts.push(text.slice(last, match.index));
    const key = `${keyBase}-${i++}`;
    if (match[1]) parts.push(/* @__PURE__ */ jsx14("code", { children: match[1].slice(1, -1) }, key));
    else if (match[2]) {
      const target = match[3];
      parts.push(openDocument && /\.md(#.*)?$/.test(target) && !/^[a-z]+:/i.test(target) ? /* @__PURE__ */ jsx14("button", { type: "button", className: "pk-md-link", onClick: () => openDocument(target.replace(/#.*$/, "")), children: match[2] }, key) : /* @__PURE__ */ jsx14("span", { className: "pk-md-ext", title: target, children: match[2] }, key));
    } else parts.push(/* @__PURE__ */ jsx14("strong", { children: match[4] }, key));
    last = pattern.lastIndex;
  }
  if (last < text.length) parts.push(text.slice(last));
  return parts;
}
var cells = (row) => row.trim().replace(/^\||\|$/g, "").split("|").map((cell) => cell.trim());
function Markdown({ text, openDocument }) {
  const lines = String(text || "").split(/\r?\n/);
  const blocks = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    const key = `b${i}`;
    if (/^```/.test(line)) {
      const body = [];
      i += 1;
      while (i < lines.length && !/^```/.test(lines[i])) body.push(lines[i++]);
      i += 1;
      blocks.push(/* @__PURE__ */ jsx14("pre", { className: "pk-md-code", children: body.join("\n") }, key));
    } else if (/^#{1,6}\s/.test(line)) {
      const level = Math.min(6, line.match(/^#+/)[0].length + 1);
      const Tag = `h${level}`;
      blocks.push(/* @__PURE__ */ jsx14(Tag, { className: "pk-md-heading", children: inline(line.replace(/^#+\s*/, ""), openDocument, key) }, key));
      i += 1;
    } else if (/^\s*\|.*\|\s*$/.test(line) && /^\s*\|[\s:|-]+\|\s*$/.test(lines[i + 1] || "")) {
      const head = cells(line);
      const rows = [];
      i += 2;
      while (i < lines.length && /^\s*\|.*\|\s*$/.test(lines[i])) rows.push(cells(lines[i++]));
      blocks.push(/* @__PURE__ */ jsx14("div", { className: "pk-table-wrap", children: /* @__PURE__ */ jsxs14("table", { className: "pk-md-table", children: [
        /* @__PURE__ */ jsx14("thead", { children: /* @__PURE__ */ jsx14("tr", { children: head.map((cell, c) => /* @__PURE__ */ jsx14("th", { children: inline(cell, openDocument, `${key}h${c}`) }, c)) }) }),
        /* @__PURE__ */ jsx14("tbody", { children: rows.map((row, r) => /* @__PURE__ */ jsx14("tr", { children: row.map((cell, c) => /* @__PURE__ */ jsx14("td", { children: inline(cell, openDocument, `${key}r${r}c${c}`) }, c)) }, r)) })
      ] }) }, key));
    } else if (/^\s*([-*]|\d+\.)\s/.test(line)) {
      const ordered = /^\s*\d+\./.test(line);
      const items = [];
      while (i < lines.length && /^\s*([-*]|\d+\.)\s/.test(lines[i])) {
        const item = lines[i].replace(/^\s*([-*]|\d+\.)\s+/, "");
        const task = /^\[( |x)\]\s/i.exec(item);
        items.push({ text: task ? item.slice(4) : item, task: task ? task[1].toLowerCase() === "x" : null, depth: /^\s{2,}/.test(lines[i]) });
        i += 1;
      }
      const List = ordered ? "ol" : "ul";
      blocks.push(/* @__PURE__ */ jsx14(List, { className: "pk-md-list", children: items.map((item, n) => /* @__PURE__ */ jsxs14("li", { "data-depth": item.depth ? "nested" : "top", "data-task": item.task == null ? void 0 : item.task ? "done" : "open", children: [
        item.task != null && /* @__PURE__ */ jsx14("span", { className: "pk-md-check", "aria-hidden": "true", children: item.task ? "\u2713" : "\u25CB" }),
        inline(item.text, openDocument, `${key}-${n}`)
      ] }, n)) }, key));
    } else if (/^>\s?/.test(line)) {
      const body = [];
      while (i < lines.length && /^>\s?/.test(lines[i])) body.push(lines[i++].replace(/^>\s?/, ""));
      blocks.push(/* @__PURE__ */ jsx14("blockquote", { className: "pk-md-quote", children: inline(body.join(" "), openDocument, key) }, key));
    } else if (/^(-{3,}|\*{3,})\s*$/.test(line)) {
      blocks.push(/* @__PURE__ */ jsx14("hr", { className: "pk-md-rule" }, key));
      i += 1;
    } else if (!line.trim()) {
      i += 1;
    } else {
      const body = [];
      while (i < lines.length && lines[i].trim() && !/^(#{1,6}\s|```|\s*([-*]|\d+\.)\s|>|\s*\|)/.test(lines[i])) body.push(lines[i++]);
      if (!body.length) body.push(lines[i++]);
      blocks.push(/* @__PURE__ */ jsx14("p", { className: "pk-md-p", children: inline(body.join(" "), openDocument, key) }, key));
    }
  }
  return /* @__PURE__ */ jsx14("div", { className: "pk-markdown", children: blocks });
}

// client/src/views/Documents.jsx
import { Fragment as Fragment4, jsx as jsx15, jsxs as jsxs15 } from "react/jsx-runtime";
var CATEGORY_ORDER = ["plans", "handoffs", "requirements", "architecture", "modules", "frontend", "records", "acceptance", "reviews"];
function resolveDocumentLink(from, target) {
  const out = [];
  for (const part of [...from.split("/").slice(0, -1), ...target.split("/")]) {
    if (part === "..") out.pop();
    else if (part && part !== ".") out.push(part);
  }
  return out.join("/");
}
function Documents({ resources, t, documentPath, openDocument }) {
  const index = resources.documents;
  const reader = resources.document;
  const documents = array(index?.data?.documents);
  const [query, setQuery] = useState9("");
  const [open, setOpen] = useState9(() => /* @__PURE__ */ new Set(["plans", "handoffs"]));
  const groups = useMemo2(() => {
    const needle = query.trim().toLowerCase();
    const map = /* @__PURE__ */ new Map();
    for (const doc of documents) {
      if (needle && !`${doc.path} ${doc.title ?? ""}`.toLowerCase().includes(needle)) continue;
      map.set(doc.category, [...map.get(doc.category) || [], doc]);
    }
    return [...map.entries()].sort(([a], [b]) => (CATEGORY_ORDER.indexOf(a) + 99) % 99 - (CATEGORY_ORDER.indexOf(b) + 99) % 99);
  }, [documents, query]);
  const current = reader?.data;
  const shown = current && current.path === documentPath ? current : null;
  const references = array(shown?.references);
  const missing = references.filter((ref) => !ref.exists);
  const follow = (target) => openDocument?.(resolveDocumentLink(shown?.path || "", target));
  return /* @__PURE__ */ jsxs15("div", { className: "pk-view pk-documents", children: [
    /* @__PURE__ */ jsx15(ViewTitle, { id: "documents", t, subtitle: t("documents.subtitle") }),
    /* @__PURE__ */ jsxs15("div", { className: "pk-documents-layout", children: [
      /* @__PURE__ */ jsx15(Section, { title: t("documents.index", { count: documents.length }), source: "document", t, className: "pk-doc-nav", children: /* @__PURE__ */ jsxs15(ResourceState, { resource: index, t, source: "document", empty: !documents.length, children: [
        /* @__PURE__ */ jsxs15("label", { className: "pk-doc-search", children: [
          t("documents.search"),
          /* @__PURE__ */ jsx15("input", { type: "search", value: query, onChange: (event) => setQuery(event.target.value) })
        ] }),
        groups.map(([category, docs]) => /* @__PURE__ */ jsxs15("details", { className: "pk-doc-category", open: Boolean(query) || open.has(category), onToggle: (event) => {
          const next = new Set(open);
          event.currentTarget.open ? next.add(category) : next.delete(category);
          setOpen(next);
        }, children: [
          /* @__PURE__ */ jsxs15("summary", { children: [
            /* @__PURE__ */ jsx15("span", { children: t(`documents.category.${category}`) === `documents.category.${category}` ? category : t(`documents.category.${category}`) }),
            /* @__PURE__ */ jsx15("span", { className: "pk-count-badge", children: docs.length })
          ] }),
          /* @__PURE__ */ jsx15("ul", { className: "pk-doc-list", children: docs.map((doc) => /* @__PURE__ */ jsx15("li", { children: /* @__PURE__ */ jsxs15("button", { type: "button", className: "pk-doc-item", "aria-current": doc.path === documentPath ? "true" : void 0, onClick: () => openDocument?.(doc.path), children: [
            /* @__PURE__ */ jsx15("span", { children: doc.title || doc.path.split("/").pop() }),
            /* @__PURE__ */ jsx15("small", { children: doc.path })
          ] }) }, doc.path)) })
        ] }, category))
      ] }) }),
      /* @__PURE__ */ jsx15(Section, { title: shown?.title || documentPath || t("documents.reader"), source: "document", t, className: "pk-doc-reader", children: !documentPath ? /* @__PURE__ */ jsx15("p", { className: "pk-note", children: t("documents.selectPrompt") }) : /* @__PURE__ */ jsx15(ResourceState, { resource: shown ? reader : { ...reader, data: null }, t, source: "document", children: shown && /* @__PURE__ */ jsxs15(Fragment4, { children: [
        /* @__PURE__ */ jsxs15("div", { className: "pk-doc-meta", children: [
          /* @__PURE__ */ jsx15("code", { children: shown.path }),
          /* @__PURE__ */ jsx15("span", { children: t("documents.bytes", { bytes: reader.meta?.bytes ?? "\u2014" }) }),
          reader.meta?.truncated && /* @__PURE__ */ jsx15(Badge, { value: "limited_evidence", t })
        ] }),
        shown.path === "DELIVERY_PLAN.md" && /* @__PURE__ */ jsx15("p", { className: "pk-banner pk-warning", children: t("documents.planNotice") }),
        references.length > 0 && /* @__PURE__ */ jsxs15("details", { className: "pk-doc-refs", open: missing.length > 0, children: [
          /* @__PURE__ */ jsx15("summary", { children: t("documents.references", { total: references.length, missing: missing.length }) }),
          /* @__PURE__ */ jsx15("ul", { children: references.map((ref) => /* @__PURE__ */ jsxs15("li", { "data-exists": ref.exists ? "true" : "false", children: [
            /* @__PURE__ */ jsx15("span", { className: "pk-ref-state", children: ref.exists ? t("documents.exists") : t("documents.missing") }),
            ref.exists && /\.md$/.test(ref.path) ? /* @__PURE__ */ jsx15("button", { type: "button", className: "pk-md-link", onClick: () => openDocument?.(ref.path), children: ref.path }) : /* @__PURE__ */ jsx15("code", { children: ref.path })
          ] }, ref.path)) })
        ] }),
        /* @__PURE__ */ jsx15("article", { className: "pk-doc-article", children: /* @__PURE__ */ jsx15(Markdown, { text: shown.text, openDocument: follow }) })
      ] }) }) })
    ] })
  ] });
}

// client/src/views/Events.jsx
import React16, { useMemo as useMemo3, useState as useState10 } from "react";
import { jsx as jsx16, jsxs as jsxs16 } from "react/jsx-runtime";
var refsOf = (event) => array(event.object_refs).map((ref) => `${ref.object_type}:${ref.object_id}`);
var haystack = (event) => [event.event_type, event.command_id, event.event_schema, `#${event.commit_seq}`, ...refsOf(event)].filter(Boolean).join(" ").toLowerCase();
function groupByCommit(events) {
  const groups = /* @__PURE__ */ new Map();
  for (const event of events) {
    const key = String(event.commit_seq);
    groups.set(key, [...groups.get(key) || [], event]);
  }
  const bigint = (value) => {
    try {
      return BigInt(value);
    } catch {
      return 0n;
    }
  };
  return [...groups.entries()].sort(([a], [b]) => bigint(b) > bigint(a) ? 1 : bigint(b) < bigint(a) ? -1 : 0).map(([seq, items]) => [seq, items.slice().sort((a, b) => (Number(a.event_index) || 0) - (Number(b.event_index) || 0))]);
}
function Events({ resources, t }) {
  const resource = resources.events;
  const events = array(resource?.data);
  const [filter, setFilter] = useState10("");
  const [query, setQuery] = useState10("");
  const types = [...new Set(events.map((event) => event.event_type).filter(Boolean))].sort();
  const needle = query.trim().toLowerCase();
  const rows = useMemo3(
    () => events.filter((event) => (!filter || event.event_type === filter) && (!needle || haystack(event).includes(needle))),
    [events, filter, needle]
  );
  const groups = useMemo3(() => groupByCommit(rows), [rows]);
  const last = events.at(-1);
  const arrived = useArrivals(events.map((event) => `${event.commit_seq}:${event.event_index}`));
  return /* @__PURE__ */ jsxs16("div", { className: "pk-view", children: [
    /* @__PURE__ */ jsx16(ViewTitle, { id: "events", t, subtitle: t("events.subtitle") }),
    /* @__PURE__ */ jsxs16(Section, { title: t("events.stream"), t, hint: t("events.hint"), aside: /* @__PURE__ */ jsx16("span", { className: "pk-match-count", "aria-live": "polite", children: t("common.shown", { shown: rows.length, total: events.length }) }), children: [
      /* @__PURE__ */ jsxs16("div", { className: "pk-timeline-tools", children: [
        /* @__PURE__ */ jsxs16("label", { className: "pk-grow", children: [
          t("events.search"),
          /* @__PURE__ */ jsx16("input", { type: "search", value: query, onChange: (event) => setQuery(event.target.value) })
        ] }),
        /* @__PURE__ */ jsxs16("label", { children: [
          t("events.filterByType"),
          /* @__PURE__ */ jsxs16("select", { value: filter, onChange: (event) => setFilter(event.target.value), children: [
            /* @__PURE__ */ jsx16("option", { value: "", children: t("common.all") }),
            types.map((type) => /* @__PURE__ */ jsx16("option", { value: type, children: type }, type))
          ] })
        ] }),
        /* @__PURE__ */ jsx16("button", { className: "pk-button pk-button-secondary", type: "button", onClick: () => resource?.refresh?.({ commit_seq: void 0, event_index: void 0 }), children: t("events.fromStart") }),
        /* @__PURE__ */ jsx16("button", { className: "pk-button", type: "button", disabled: !last, onClick: () => resource?.refresh?.({ commit_seq: String(last.commit_seq), event_index: Number(last.event_index) || 0 }), children: t("events.more") })
      ] }),
      /* @__PURE__ */ jsx16(ResourceState, { resource, t, empty: !events.length, emptyText: t("events.noEvents"), children: rows.length === 0 ? /* @__PURE__ */ jsx16("p", { className: "pk-quiet", children: t("events.noMatch") }) : /* @__PURE__ */ jsx16("ol", { className: "pk-commits", children: groups.map(([seq, items], g) => /* @__PURE__ */ jsxs16("li", { className: `pk-commit ${stagger(g)}`, children: [
        /* @__PURE__ */ jsxs16("h4", { className: "pk-commit-seq", children: [
          /* @__PURE__ */ jsxs16("span", { children: [
            "#",
            seq
          ] }),
          /* @__PURE__ */ jsx16("small", { children: t("events.entries", { count: items.length }) })
        ] }),
        /* @__PURE__ */ jsx16("ul", { className: "pk-commit-events", children: items.map((event) => {
          const key = `${event.commit_seq}:${event.event_index}`;
          return /* @__PURE__ */ jsxs16("li", { className: arrived.has(key) ? "pk-arrived" : "", children: [
            /* @__PURE__ */ jsxs16("code", { className: "pk-event-index", children: [
              ".",
              event.event_index
            ] }),
            /* @__PURE__ */ jsx16("strong", { className: "pk-event-type", children: event.event_type }),
            /* @__PURE__ */ jsxs16("span", { className: "pk-event-meta", children: [
              event.command_id && /* @__PURE__ */ jsx16("code", { title: t("events.command"), children: event.command_id }),
              refsOf(event).map((ref) => /* @__PURE__ */ jsx16("code", { className: "pk-ref", children: ref }, ref))
            ] })
          ] }, key);
        }) })
      ] }, seq)) }) })
    ] })
  ] });
}

// client/src/views/Design.jsx
import React17, { useState as useState11 } from "react";
import { jsx as jsx17, jsxs as jsxs17 } from "react/jsx-runtime";
var STATUS_GLYPH = { tested: "\u2713", unwired: "\u25B3", preview: "\u25C7" };
var DESIGN_PILLARS = [
  { id: "memory", items: [
    { id: "ledger", paths: ["src/project_kernel/data/store/uow.py", "tests/p15 step A"], status: "tested" },
    { id: "unknown", paths: ["tests/p14_science_demo/science_executor.py", "tests/p15 step B"], status: "tested" },
    { id: "idempotent", paths: ["src/project_kernel/data/store/uow.py", "tests/p15 step D"], status: "tested" },
    { id: "knowledge", paths: ["src/project_kernel/knowledge", "tests/p08_knowledge"], status: "unwired" }
  ] },
  { id: "trust", items: [
    { id: "forged", paths: ["tests/p14_science_demo/science_checker.py", "tests/p14", "tests/p15"], status: "tested" },
    { id: "human", paths: ["src/project_kernel/interfaces/rpc/policy.py", "tests/p14", "tests/p15"], status: "tested" },
    { id: "rules", paths: ["src/project_kernel/domain/design/rules.py", "tests/p15"], status: "tested" },
    { id: "voided", paths: ["src/project_kernel/application/delivery", "tests/p15 step E"], status: "tested" },
    { id: "reconcile", paths: ["src/project_kernel/application/delivery", "tests/p15 step F"], status: "tested" }
  ] },
  { id: "view", items: [
    { id: "readmodel", paths: ["src/project_kernel/data/queries/service.py", "tests/p15 step G"], status: "tested" },
    { id: "tree", paths: ["docs/modules/registry.json"], status: "tested", doc: true },
    { id: "panel", paths: ["adapters/agh-plugin/client"], status: "tested" }
  ] },
  { id: "integration", items: [
    { id: "plugin", paths: ["adapters/agh-plugin", "bridge/protocol"], status: "tested" },
    { id: "skill", paths: ["docs/records/skills/registry.json"], status: "preview" },
    { id: "exchange", paths: ["docs/architecture/agent-exchange-and-live-forms.md"], status: "preview" },
    { id: "workspace", paths: ["docs/frontend/workspace-project-design.md"], status: "preview" }
  ] }
];
var ALL_ITEMS = DESIGN_PILLARS.flatMap((pillar) => pillar.items);
function StatusMark({ status, t }) {
  return /* @__PURE__ */ jsxs17("span", { className: "pk-design-status", "data-status": status, children: [
    /* @__PURE__ */ jsx17("span", { "aria-hidden": "true", children: STATUS_GLYPH[status] }),
    t(`design.status.${status}`)
  ] });
}
function Design({ t }) {
  const [filter, setFilter] = useState11("all");
  const counts = { all: ALL_ITEMS.length };
  for (const item of ALL_ITEMS) counts[item.status] = (counts[item.status] || 0) + 1;
  return /* @__PURE__ */ jsxs17("div", { className: "pk-view pk-design", children: [
    /* @__PURE__ */ jsx17(ViewTitle, { id: "design", t, subtitle: t("design.subtitle") }),
    /* @__PURE__ */ jsxs17(Section, { title: t("design.map"), source: "document", t, hint: t("design.mapTip"), aside: /* @__PURE__ */ jsx17("div", { className: "pk-filter", role: "group", "aria-label": t("design.col.status"), children: ["all", "tested", "unwired", "preview"].map((key) => /* @__PURE__ */ jsxs17("button", { type: "button", className: "pk-filter-chip", "data-status": key, "aria-pressed": filter === key, onClick: () => setFilter(key), children: [
      key === "all" ? t("design.all") : t(`design.status.${key}`),
      /* @__PURE__ */ jsx17("b", { children: counts[key] || 0 })
    ] }, key)) }), children: [
      /* @__PURE__ */ jsxs17("div", { className: "pk-design-head", "aria-hidden": "true", children: [
        /* @__PURE__ */ jsx17("span", { children: t("design.col.item") }),
        /* @__PURE__ */ jsx17("span", { children: t("design.col.how") }),
        /* @__PURE__ */ jsx17("span", { children: t("design.col.path") }),
        /* @__PURE__ */ jsx17("span", { children: t("design.col.status") })
      ] }),
      DESIGN_PILLARS.map((pillar) => {
        const items = pillar.items.filter((item) => filter === "all" || item.status === filter);
        if (!items.length) return null;
        return /* @__PURE__ */ jsxs17("section", { className: "pk-pillar", "data-pillar": pillar.id, "aria-label": t(`design.pillar.${pillar.id}`), children: [
          /* @__PURE__ */ jsxs17("h4", { children: [
            t(`design.pillar.${pillar.id}`),
            /* @__PURE__ */ jsx17("small", { children: items.length })
          ] }),
          /* @__PURE__ */ jsx17("ul", { children: items.map((item, i) => /* @__PURE__ */ jsxs17("li", { className: `pk-design-row pk-enter pk-i-${Math.min(i, 15)}`, "data-status": item.status, children: [
            /* @__PURE__ */ jsxs17("div", { className: "pk-design-pain", children: [
              /* @__PURE__ */ jsx17("strong", { children: t(`design.${item.id}.name`) }),
              /* @__PURE__ */ jsx17("span", { children: t(`design.${item.id}.pain`) })
            ] }),
            /* @__PURE__ */ jsx17("p", { className: "pk-design-how", children: t(`design.${item.id}.how`) }),
            /* @__PURE__ */ jsx17("ul", { className: "pk-design-paths", children: item.paths.map((path) => /* @__PURE__ */ jsx17("li", { children: /* @__PURE__ */ jsx17("code", { children: path }) }, path)) }),
            /* @__PURE__ */ jsxs17("div", { className: "pk-design-state", children: [
              /* @__PURE__ */ jsx17(StatusMark, { status: item.status, t }),
              item.doc && /* @__PURE__ */ jsx17("small", { children: t("design.note.document") })
            ] })
          ] }, item.id)) })
        ] }, pillar.id);
      })
    ] })
  ] });
}

// client/src/views/index.jsx
var VIEW_GROUPS = [
  { id: "project", views: ["overview", "design", "workspace", "structure", "requirements"] },
  { id: "run", views: ["execution", "permissions", "environment"] },
  { id: "govern", views: ["versions", "events", "errors"] },
  { id: "records", views: ["documents", "skills", "knowledge"] }
];
var VIEW_IDS = VIEW_GROUPS.flatMap((group) => group.views);
var VIEWS = { overview: Overview, design: Design, structure: Structure, requirements: Requirements, permissions: Permissions, execution: Execution, knowledge: Knowledge, errors: Errors, skills: Skills, environment: Environment, versions: Versions, workspace: WorkspaceProject, documents: Documents, events: Events };

// client/src/data/usePoll.js
import { useCallback, useEffect as useEffect2, useMemo as useMemo4, useRef as useRef2, useState as useState12 } from "react";

// client/src/data/services.js
var SERVICES = {
  overview: "pk.overview",
  compare: "pk.compare",
  approvals: "pk.approvals",
  timeline: "pk.timeline",
  trace: "pk.trace",
  coverage: "pk.coverage",
  environment: "pk.environment",
  operation: "pk.operation",
  tree: "pk.tree",
  skills: "pk.skills",
  events: "pk.events"
};
var SERVICE_NAMES = Object.freeze(SERVICES);
function serviceError(error) {
  return String(error?.message ?? error ?? "Unknown service error");
}
async function callService(ctx, shortName, input = {}) {
  const name = SERVICES[shortName] ?? (Object.values(SERVICES).includes(shortName) ? shortName : null);
  if (!name) throw new TypeError(`Unknown read-only service: ${shortName}`);
  if (!ctx?.agnes?.services?.call) throw new Error("client service requires an active session and services capability");
  return ctx.agnes.services.call(name, Object.fromEntries(Object.entries(input).filter(([, value]) => value !== void 0)));
}
function unpackResponse(response) {
  if (response && typeof response === "object" && !Array.isArray(response) && Object.prototype.hasOwnProperty.call(response, "data")) {
    const { data, ...envelope } = response;
    const meta = response.meta ?? envelope;
    return { data, meta: meta && typeof meta === "object" ? meta : {} };
  }
  return { data: response, meta: {} };
}

// client/src/data/poll-controller.js
var empty = () => ({ phase: "loading", data: void 0, meta: void 0, error: void 0 });
function createPollController({
  request,
  onState,
  interval = 2500,
  schedule = (callback, delay) => setTimeout(callback, delay),
  unschedule = (id) => clearTimeout(id)
}) {
  let active = false;
  let disposed = false;
  let generation = 0;
  let timer;
  let failures = 0;
  let input = {};
  let state = empty();
  const emit = (next) => {
    state = next;
    onState(next);
  };
  const clearTimer = () => {
    if (timer !== void 0) unschedule(timer);
    timer = void 0;
  };
  const tick = async () => {
    if (!active || disposed) return void 0;
    clearTimer();
    const token = ++generation;
    try {
      const response = await request({ ...input });
      if (token !== generation || !active || disposed) return void 0;
      const { data, meta } = unpackResponse(response);
      failures = 0;
      emit({
        phase: data === null || data === void 0 || data?.data_state === "no_data" ? "empty" : "ready",
        data,
        meta,
        error: void 0,
        at: Date.now()
      });
    } catch (error) {
      if (token !== generation || !active || disposed) return void 0;
      failures += 1;
      emit({ ...state, phase: "unavailable", error: serviceError(error) });
    }
    if (token === generation && active && !disposed) {
      timer = schedule(tick, failures ? Math.min(1e4, interval * 2 ** (failures - 1)) : interval);
    }
    return state;
  };
  return {
    start(nextInput = {}) {
      if (disposed) return;
      generation += 1;
      clearTimer();
      input = nextInput;
      failures = 0;
      active = true;
      emit(empty());
      return tick();
    },
    refresh() {
      return tick();
    },
    pause() {
      active = false;
      generation += 1;
      clearTimer();
    },
    dispose() {
      disposed = true;
      active = false;
      generation += 1;
      clearTimer();
    }
  };
}

// client/src/data/usePoll.js
function usePoll(ctx, shortName, {
  visible = true,
  active = true,
  asOfSeq = null,
  sessionId,
  interval = 2500,
  manual = false
} = {}) {
  const [state, setState] = useState12({ phase: manual ? "disabled" : "loading" });
  const [payload, setPayload] = useState12({ sessionId, asOfSeq, input: {} });
  const [revision, setRevision] = useState12(0);
  const [manualSession, enable] = useState12(manual ? void 0 : sessionId);
  const manuallyEnabled = !manual || manualSession === sessionId;
  const input = useMemo4(() => {
    const next = payload.sessionId === sessionId ? { ...payload.input } : {};
    if (payload.asOfSeq !== asOfSeq) delete next.page_token;
    if (asOfSeq !== null) next.as_of_seq = String(asOfSeq);
    return next;
  }, [payload, asOfSeq, sessionId]);
  const scopeKey = `${sessionId ?? ""}:${JSON.stringify(input)}`;
  const controller = useMemo4(() => createPollController({
    request: (nextInput) => callService(ctx, shortName, nextInput),
    onState: (next) => setState({ ...next, scopeKey }),
    interval
  }), [ctx, shortName, interval, scopeKey]);
  useEffect2(() => () => controller.pause(), [controller]);
  useEffect2(() => {
    if (visible && active && manuallyEnabled) controller.start(input);
    else controller.pause();
    return () => controller.pause();
  }, [controller, visible, active, manuallyEnabled, input, revision]);
  const refresh = useCallback((nextPayload) => {
    if (nextPayload) setPayload((current) => ({
      sessionId,
      asOfSeq,
      input: { ...current.sessionId === sessionId ? current.input : {}, ...nextPayload }
    }));
    enable(sessionId);
    setRevision((value) => value + 1);
  }, [sessionId, asOfSeq]);
  return { ...state.scopeKey === scopeKey ? state : { phase: manual && !manuallyEnabled ? "disabled" : "loading" }, refresh };
}
function usePanelVisibility() {
  const [visible, setVisible] = useState12(false);
  const target = useRef2(null);
  useEffect2(() => {
    if (typeof document === "undefined") return void 0;
    let intersecting = typeof IntersectionObserver !== "function";
    const update = () => setVisible(intersecting && document.visibilityState !== "hidden");
    document.addEventListener("visibilitychange", update);
    let observer;
    if (typeof IntersectionObserver === "function" && target.current) {
      observer = new IntersectionObserver((entries2) => {
        intersecting = entries2.some((entry) => entry.isIntersecting);
        update();
      }, { threshold: 0.01 });
      observer.observe(target.current);
    }
    update();
    return () => {
      document.removeEventListener("visibilitychange", update);
      observer?.disconnect();
    };
  }, []);
  return { visible, target };
}

// client/src/app/Shell.jsx
import { jsx as jsx18, jsxs as jsxs18 } from "react/jsx-runtime";
var noopSubscribe = () => () => {
};
var VIEW_SERVICES = {
  overview: ["compare"],
  design: [],
  structure: ["tree", "trace"],
  requirements: ["coverage", "trace"],
  permissions: [],
  execution: ["compare", "operation"],
  knowledge: [],
  errors: ["compare", "timeline"],
  skills: ["skills"],
  environment: ["environment"],
  versions: ["timeline"],
  workspace: ["tree"],
  documents: ["documents", "document"],
  events: ["events"]
};
var DOCUMENT_SERVICES = ["tree", "skills", "documents", "document"];
function useHostSnapshot(service, fallback) {
  const subscribe = useCallback2((listener) => service?.subscribe?.(listener) ?? noopSubscribe(), [service]);
  const read = useCallback2(() => service?.getSnapshot?.() ?? fallback, [service, fallback]);
  return useSyncExternalStore(subscribe, read, read);
}
function metadataIsStale(meta) {
  if (!meta) return false;
  const freshness = meta.freshness ?? {};
  return freshness.projection_stale === true || Number(freshness.projection_lag_seq ?? 0) > 0 || ["stale", "source_failed", "incomplete"].includes(freshness.state) || ["incomplete", "unknown"].includes(meta.completeness) || Boolean(meta.gaps?.length || meta.required_missing?.length);
}
function Shell({ ctx, config = {}, initialView = "overview", initialOpen = true }) {
  const [view, setView] = useState13(VIEW_IDS.includes(initialView) ? initialView : "overview");
  const [open, setOpen] = useState13(initialOpen);
  const [wide, setWide] = useState13(false);
  const [asOfSeq, setAsOfSeq] = useState13(null);
  const [maxSeq, setMaxSeq] = useState13("0");
  const [documentPath, setDocumentPath] = useState13(null);
  const theme = useHostSnapshot(ctx?.theme, "dark");
  const locale = useHostSnapshot(ctx?.locale, "zh-CN");
  const sessionId = useHostSnapshot(ctx?.session, null);
  const t = useMemo5(() => ctx?.locale?.bind?.("project-kernel") ?? createTranslator(locale), [ctx?.locale, locale]);
  const { target, visible: inViewport } = usePanelVisibility();
  const visible = open && inViewport;
  const active = !ctx?.session || Boolean(sessionId);
  const needs = VIEW_SERVICES[view] ?? [];
  const options = (service, extra = {}) => ({
    visible: service === "approvals" || service === "overview" ? inViewport : visible,
    active: active && (service === "overview" || service === "approvals" || needs.includes(service)),
    asOfSeq: DOCUMENT_SERVICES.includes(service) ? null : asOfSeq,
    sessionId,
    ...extra
  });
  const approvalsResource = usePoll(ctx, "approvals", options("approvals"));
  const hasPending = Number(approvalsResource.data?.pending_count ?? 0) > 0;
  const loadedResources = {
    overview: usePoll(ctx, "overview", options("overview")),
    compare: usePoll(ctx, "compare", { ...options("compare"), active: active && (hasPending || needs.includes("compare")), visible: hasPending ? inViewport : visible }),
    approvals: approvalsResource,
    timeline: usePoll(ctx, "timeline", options("timeline")),
    trace: usePoll(ctx, "trace", options("trace")),
    coverage: usePoll(ctx, "coverage", options("coverage")),
    environment: usePoll(ctx, "environment", options("environment")),
    operation: usePoll(ctx, "operation", options("operation", { manual: true })),
    tree: usePoll(ctx, "tree", options("tree", { interval: 1e4 })),
    skills: usePoll(ctx, "skills", options("skills", { interval: 1e4 })),
    documents: usePoll(ctx, "documents", options("documents", { interval: 15e3 })),
    document: usePoll(ctx, "document", options("document", { manual: true, interval: 15e3 })),
    events: usePoll(ctx, "events", options("events"))
  };
  const resources = active ? loadedResources : Object.fromEntries(Object.entries(loadedResources).map(([name, resource]) => [name, {
    phase: "unavailable",
    error: t("shell.sessionRequired"),
    refresh: resource.refresh
  }]));
  const meta = resources.overview.meta;
  const error = resources.overview.error;
  const connected = active && resources.overview.phase === "ready";
  const gaps = [...meta?.gaps ?? [], ...meta?.required_missing ?? []];
  const pendingCount = Number(resources.approvals?.data?.pending_count ?? 0);
  const refresh = () => ["overview", "approvals", ...needs].forEach((name) => {
    if (!["operation", "document"].includes(name) || resources[name].phase !== "disabled") resources[name]?.refresh();
  });
  useEffect3(() => {
    const head = meta?.freshness?.store_head_seq ?? meta?.as_of_seq;
    if (head !== null && head !== void 0 && /^(0|[1-9][0-9]*)$/.test(String(head))) {
      setMaxSeq((current) => BigInt(head) > BigInt(current) ? String(head) : current);
    }
  }, [meta]);
  useEffect3(() => {
    setAsOfSeq(null);
    setMaxSeq("0");
  }, [sessionId]);
  useEffect3(() => {
    if (pendingCount > 0 && asOfSeq == null) setOpen(true);
  }, [pendingCount, asOfSeq]);
  useEffect3(() => {
    if (!open || typeof document === "undefined") return void 0;
    const onKey = (event) => {
      if (event.key === "Escape" && !event.defaultPrevented) setOpen(false);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open]);
  const CurrentView = VIEWS[view];
  const openDocument = (path) => {
    setDocumentPath(path);
    setView("documents");
    resources.document?.refresh?.({ path });
  };
  const select = (id) => {
    setView(id);
    setOpen(true);
  };
  const navigateWithKeys = (event, id) => {
    const change = event.key === "ArrowDown" ? 1 : event.key === "ArrowUp" ? -1 : 0;
    if (!change && event.key !== "Home" && event.key !== "End") return;
    event.preventDefault();
    const index = VIEW_IDS.indexOf(id);
    const next = event.key === "Home" ? 0 : event.key === "End" ? VIEW_IDS.length - 1 : (index + change + VIEW_IDS.length) % VIEW_IDS.length;
    setView(VIEW_IDS[next]);
    event.currentTarget.closest('[role="tablist"]')?.querySelector(`#pk-tab-${VIEW_IDS[next]}`)?.focus();
  };
  const groupOf = VIEW_GROUPS.find((group) => group.views.includes(view));
  return /* @__PURE__ */ jsxs18("section", { ref: target, className: "pk-root", "data-theme": theme, "data-view": view, "data-open": open ? "true" : "false", "data-wide": wide ? "true" : "false", children: [
    /* @__PURE__ */ jsxs18("button", { type: "button", className: "pk-launcher", "aria-expanded": open, "aria-controls": "pk-drawer", onClick: () => setOpen(!open), children: [
      /* @__PURE__ */ jsx18("span", { className: "pk-launcher-mark", "aria-hidden": "true", children: "PK" }),
      /* @__PURE__ */ jsx18("span", { className: "pk-launcher-label", children: t("shell.title") }),
      pendingCount > 0 && /* @__PURE__ */ jsx18("span", { className: "pk-launcher-badge", "aria-label": t("permissions.pendingDrawer", { count: pendingCount }), children: pendingCount }),
      /* @__PURE__ */ jsx18("span", { className: "pk-live", "data-state": connected ? "on" : "off", "aria-hidden": "true" })
    ] }),
    /* @__PURE__ */ jsxs18("div", { id: "pk-drawer", className: "pk-drawer", role: "dialog", "aria-modal": "false", "aria-label": t("shell.title"), hidden: !open, children: [
      /* @__PURE__ */ jsxs18("header", { className: "pk-shell-header", children: [
        /* @__PURE__ */ jsxs18("div", { className: "pk-shell-branding", children: [
          /* @__PURE__ */ jsx18("span", { className: "pk-brand-mark", "aria-hidden": "true", children: "PK" }),
          /* @__PURE__ */ jsxs18("div", { children: [
            /* @__PURE__ */ jsx18("h2", { children: config.publicConfig?.title ?? t("shell.title") }),
            /* @__PURE__ */ jsxs18("nav", { className: "pk-breadcrumb", "aria-label": t("shell.breadcrumb"), children: [
              /* @__PURE__ */ jsx18("span", { children: groupOf ? t(`group.${groupOf.id}`) : "" }),
              /* @__PURE__ */ jsx18("span", { "aria-hidden": "true", children: "/" }),
              /* @__PURE__ */ jsx18("strong", { children: t(`navigation.${view}`) })
            ] })
          ] })
        ] }),
        /* @__PURE__ */ jsxs18("div", { className: "pk-shell-actions", children: [
          /* @__PURE__ */ jsx18("span", { className: "pk-live", "data-state": connected ? "on" : "off", children: t(connected ? "shell.connected" : "shell.disconnected") }),
          /* @__PURE__ */ jsx18("button", { type: "button", className: "pk-button", onClick: refresh, children: t("shell.refresh") }),
          /* @__PURE__ */ jsx18("button", { type: "button", className: "pk-icon-button", "aria-pressed": wide, onClick: () => setWide(!wide), "aria-label": t(wide ? "shell.narrow" : "shell.widen"), title: t(wide ? "shell.narrow" : "shell.widen"), children: wide ? "\u21E5" : "\u21E4" }),
          /* @__PURE__ */ jsx18("button", { type: "button", className: "pk-icon-button", onClick: () => setOpen(false), "aria-label": t("shell.close"), title: t("shell.close"), children: "\xD7" })
        ] })
      ] }),
      (!active || error) && /* @__PURE__ */ jsxs18("div", { className: "pk-banner pk-warning", role: "status", children: [
        /* @__PURE__ */ jsx18("strong", { children: t("shell.sessionRequired") }),
        error && /* @__PURE__ */ jsx18("p", { children: t("shell.connectionError", { error }) })
      ] }),
      /* @__PURE__ */ jsx18(PermissionNotice, { resource: resources.approvals, compare: resources.compare, t, asOfSeq }),
      /* @__PURE__ */ jsxs18("div", { className: "pk-shell-content", children: [
        /* @__PURE__ */ jsx18("aside", { className: "pk-shell-nav", children: /* @__PURE__ */ jsx18("div", { role: "tablist", "aria-orientation": "vertical", "aria-label": t("shell.title"), className: "pk-nav", children: VIEW_GROUPS.map((group) => /* @__PURE__ */ jsxs18("div", { className: "pk-nav-group", role: "presentation", children: [
          /* @__PURE__ */ jsx18("p", { className: "pk-nav-group-title", role: "presentation", children: t(`group.${group.id}`) }),
          group.views.map((id) => /* @__PURE__ */ jsxs18(
            "button",
            {
              type: "button",
              id: `pk-tab-${id}`,
              role: "tab",
              "aria-selected": view === id,
              "aria-controls": "pk-view-panel",
              tabIndex: view === id ? 0 : -1,
              className: `pk-nav-item ${view === id ? "is-active" : ""}`,
              onKeyDown: (event) => navigateWithKeys(event, id),
              onClick: () => select(id),
              children: [
                /* @__PURE__ */ jsx18("span", { children: t(`navigation.${id}`) }),
                id === "permissions" && pendingCount > 0 && /* @__PURE__ */ jsx18("span", { className: "pk-count-badge", children: pendingCount })
              ]
            },
            id
          ))
        ] }, group.id)) }) }),
        /* @__PURE__ */ jsxs18("main", { className: "pk-shell-main", children: [
          /* @__PURE__ */ jsx18("div", { id: "pk-view-panel", className: "pk-view-scroll", role: "tabpanel", "aria-labelledby": `pk-tab-${view}`, children: /* @__PURE__ */ jsx18("div", { className: "pk-enter", children: /* @__PURE__ */ jsx18(CurrentView, { resources, t, asOfSeq, setAsOfSeq, maxSeq, documentPath, openDocument, navigate: select }) }, view) }),
          /* @__PURE__ */ jsx18("footer", { className: "pk-view-metadata", children: /* @__PURE__ */ jsxs18("div", { className: `pk-watermarks ${metadataIsStale(meta) ? "pk-stale" : ""}`, "aria-live": "polite", children: [
            asOfSeq !== null && /* @__PURE__ */ jsx18("span", { className: "pk-history", children: t("shell.history", { seq: asOfSeq }) }),
            /* @__PURE__ */ jsxs18("span", { children: [
              t("shell.asOf"),
              " ",
              /* @__PURE__ */ jsxs18("code", { children: [
                "#",
                meta?.as_of_seq ?? "\u2014"
              ] })
            ] }),
            /* @__PURE__ */ jsxs18("span", { children: [
              t("shell.head"),
              " ",
              /* @__PURE__ */ jsxs18("code", { children: [
                "#",
                meta?.freshness?.store_head_seq ?? "\u2014"
              ] })
            ] }),
            /* @__PURE__ */ jsxs18("span", { children: [
              t("shell.completeness"),
              " ",
              /* @__PURE__ */ jsx18("strong", { children: meta?.completeness ?? "\u2014" })
            ] }),
            /* @__PURE__ */ jsxs18("span", { children: [
              t("shell.freshness"),
              " ",
              /* @__PURE__ */ jsx18("strong", { children: meta?.freshness?.state ?? "\u2014" })
            ] }),
            /* @__PURE__ */ jsx18(Info, { text: t("shell.watermarkTip") }),
            !meta && /* @__PURE__ */ jsx18("small", { children: t("shell.noMetadata") }),
            asOfSeq !== null && /* @__PURE__ */ jsx18("button", { type: "button", className: "pk-text-button", onClick: () => setAsOfSeq(null), children: t("shell.current") }),
            gaps.length > 0 && /* @__PURE__ */ jsxs18("details", { className: "pk-gaps", children: [
              /* @__PURE__ */ jsx18("summary", { children: t("shell.gaps", { count: gaps.length }) }),
              /* @__PURE__ */ jsx18("ul", { children: gaps.map((gap, index) => /* @__PURE__ */ jsx18("li", { children: /* @__PURE__ */ jsx18("code", { children: typeof gap === "string" ? gap : JSON.stringify(gap) }) }, index)) })
            ] })
          ] }) })
        ] })
      ] })
    ] })
  ] });
}

// client/src/main.jsx
import { jsx as jsx19 } from "react/jsx-runtime";
function apply(ctx, config = {}) {
  const offLocale = ctx.locale?.register?.("project-kernel", messages);
  const offPanel = ctx.slots.register("workbench.panel", () => /* @__PURE__ */ jsx19(Shell, { ctx, config }), { priority: 0 });
  let disposed = false;
  const dispose = () => {
    if (disposed) return;
    disposed = true;
    offPanel?.();
    offLocale?.();
  };
  ctx.effect?.(() => dispose);
  return dispose;
}
export {
  apply
};
