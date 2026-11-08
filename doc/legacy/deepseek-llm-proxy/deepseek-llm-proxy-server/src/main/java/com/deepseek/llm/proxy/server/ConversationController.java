package com.deepseek.llm.proxy.server;

import com.deepseek.llm.proxy.core.model.Conversation;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * 会话管理 REST 端点
 * <p>
 * 让接入方可以：
 * <ul>
 *   <li>列出某用户的会话（分页）</li>
 *   <li>查看会话详情（含完整 messages）</li>
 *   <li>创建新会话（用于预先创建 sessionId 再发起 chat）</li>
 *   <li>更新会话标题</li>
 *   <li>删除指定会话</li>
 *   <li>清空某用户在某 Provider 下的所有会话</li>
 * </ul>
 * </p>
 */
@RestController
@RequestMapping("/api/v1/llm-proxy/conversations")
public class ConversationController {

    private static final Logger log = LoggerFactory.getLogger(ConversationController.class);

    private final ConversationService conversationService;

    public ConversationController(ConversationService conversationService) {
        this.conversationService = conversationService;
    }

    /**
     * 创建会话
     * <p>POST /api/v1/llm-proxy/conversations</p>
     * <p>Body: {"userId": "...", "providerId": "...", "tenantId": "...", "title": "..."}</p>
     */
    @PostMapping
    public ResponseEntity<?> create(@RequestBody Map<String, Object> body) {
        String userId = (String) body.get("userId");
        String providerId = (String) body.get("providerId");
        String tenantId = (String) body.get("tenantId");
        String title = (String) body.get("title");

        if (userId == null || userId.isEmpty()) {
            return ResponseEntity.badRequest().body(Map.of(
                    "code", "INVALID_REQUEST",
                    "message", "userId 不能为空"
            ));
        }
        if (providerId == null || providerId.isEmpty()) {
            return ResponseEntity.badRequest().body(Map.of(
                    "code", "INVALID_REQUEST",
                    "message", "providerId 不能为空"
            ));
        }

        String sessionId = conversationService.createSession(userId, providerId, tenantId, title);
        Map<String, Object> resp = new HashMap<>();
        resp.put("sessionId", sessionId);
        resp.put("userId", userId);
        resp.put("providerId", providerId);
        resp.put("title", title == null ? "新对话" : title);
        return ResponseEntity.ok(resp);
    }

    /**
     * 列出某用户的会话
     * <p>GET /api/v1/llm-proxy/conversations?userId=...&limit=20&offset=0</p>
     */
    @GetMapping
    public ResponseEntity<?> list(@RequestParam String userId,
                                  @RequestParam(required = false) Integer limit,
                                  @RequestParam(required = false) Integer offset) {
        if (userId == null || userId.isEmpty()) {
            return ResponseEntity.badRequest().body(Map.of(
                    "code", "INVALID_REQUEST",
                    "message", "userId 不能为空"
            ));
        }
        List<Conversation> list = conversationService.listByUser(userId, limit, offset);
        return ResponseEntity.ok(Map.of(
                "userId", userId,
                "total", list.size(),
                "conversations", list
        ));
    }

    /**
     * 查看会话详情（含完整 messages）
     * <p>GET /api/v1/llm-proxy/conversations/{sessionId}?userId=...</p>
     * <p>必须传 userId 用于归属权校验</p>
     */
    @GetMapping("/{sessionId}")
    public ResponseEntity<?> get(@PathVariable String sessionId,
                                 @RequestParam String userId) {
        if (userId == null || userId.isEmpty()) {
            return ResponseEntity.badRequest().body(Map.of(
                    "code", "INVALID_REQUEST",
                    "message", "userId 不能为空"
            ));
        }
        if (!conversationService.checkOwnership(sessionId, userId)) {
            return ResponseEntity.status(403).body(Map.of(
                    "code", "AUTH_FAILED",
                    "message", "会话归属权校验失败"
            ));
        }
        Conversation conv = conversationService.get(sessionId);
        if (conv == null) {
            return ResponseEntity.status(404).body(Map.of(
                    "code", "CONVERSATION_NOT_FOUND",
                    "message", "会话不存在: " + sessionId
            ));
        }
        return ResponseEntity.ok(conv);
    }

    /**
     * 更新会话标题
     * <p>PUT /api/v1/llm-proxy/conversations/{sessionId}/title?userId=...</p>
     */
    @PutMapping("/{sessionId}/title")
    public ResponseEntity<?> updateTitle(@PathVariable String sessionId,
                                         @RequestParam String userId,
                                         @RequestBody Map<String, String> body) {
        if (userId == null || userId.isEmpty()) {
            return ResponseEntity.badRequest().body(Map.of(
                    "code", "INVALID_REQUEST",
                    "message", "userId 不能为空"
            ));
        }
        if (!conversationService.checkOwnership(sessionId, userId)) {
            return ResponseEntity.status(403).body(Map.of(
                    "code", "AUTH_FAILED",
                    "message", "会话归属权校验失败"
            ));
        }
        String title = body == null ? null : body.get("title");
        if (title == null || title.isEmpty()) {
            return ResponseEntity.badRequest().body(Map.of(
                    "code", "INVALID_REQUEST",
                    "message", "title 不能为空"
            ));
        }
        boolean ok = conversationService.updateTitle(sessionId, title);
        if (!ok) {
            return ResponseEntity.status(404).body(Map.of(
                    "code", "CONVERSATION_NOT_FOUND",
                    "message", "会话不存在或更新失败: " + sessionId
            ));
        }
        return ResponseEntity.ok(Map.of(
                "ok", true,
                "sessionId", sessionId,
                "title", title
        ));
    }

    /**
     * 删除指定会话
     * <p>DELETE /api/v1/llm-proxy/conversations/{sessionId}?userId=...</p>
     */
    @DeleteMapping("/{sessionId}")
    public ResponseEntity<?> delete(@PathVariable String sessionId,
                                    @RequestParam String userId) {
        if (userId == null || userId.isEmpty()) {
            return ResponseEntity.badRequest().body(Map.of(
                    "code", "INVALID_REQUEST",
                    "message", "userId 不能为空"
            ));
        }
        if (!conversationService.checkOwnership(sessionId, userId)) {
            return ResponseEntity.status(403).body(Map.of(
                    "code", "AUTH_FAILED",
                    "message", "会话归属权校验失败"
            ));
        }
        boolean ok = conversationService.delete(sessionId);
        if (!ok) {
            return ResponseEntity.status(404).body(Map.of(
                    "code", "CONVERSATION_NOT_FOUND",
                    "message", "会话不存在或删除失败: " + sessionId
            ));
        }
        return ResponseEntity.ok(Map.of(
                "ok", true,
                "sessionId", sessionId
        ));
    }

    /**
     * 清空某用户在某 Provider 下的所有会话
     * <p>DELETE /api/v1/llm-proxy/conversations?userId=...&providerId=...</p>
     */
    @DeleteMapping
    public ResponseEntity<?> clear(@RequestParam String userId,
                                   @RequestParam(required = false) String providerId) {
        if (userId == null || userId.isEmpty()) {
            return ResponseEntity.badRequest().body(Map.of(
                    "code", "INVALID_REQUEST",
                    "message", "userId 不能为空"
            ));
        }
        int n = conversationService.clearByUser(userId, providerId);
        return ResponseEntity.ok(Map.of(
                "ok", true,
                "userId", userId,
                "providerId", providerId,
                "deleted", n
        ));
    }
}
