package com.deepseek.llm.proxy.server.prompt;

import com.deepseek.llm.proxy.core.prompt.PromptDefinition;
import com.deepseek.llm.proxy.core.prompt.PromptException;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.DirectoryStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.List;

/**
 * Classpath 提示词加载器
 * <p>
 * 扫描 classpath 下指定目录（默认 {@code prompts/}），加载所有 {@code .txt} 文件为提示词模板。
 * </p>
 * <p>
 * 目录约定：
 * <ul>
 *   <li>{@code prompts/<providerId>/<scene>.txt} — 归属某 Provider 的提示词</li>
 *   <li>{@code prompts/_global/<scene>.txt} — 通用提示词（不绑定 Provider）</li>
 *   <li>{@code prompts/_shared/<fragment>.txt} — 共享片段（不作为独立模板，仅用于 include）</li>
 *   <li>{@code prompts/_manifest.json} — 可选清单文件（声明变量、描述等元信息）</li>
 * </ul>
 * </p>
 * <p>
 * 文件名约定：{@code <scene>.txt} 中的 scene 即作为 promptId。例如：
 * {@code prompts/deepseek-free/ocr-default.txt} → promptId="ocr-default", providerId="deepseek-free", scene="ocr-default"
 * </p>
 */
public class ClasspathPromptLoader {

    private final String classpathLocation;
    private final PromptTemplateEngine engine;

    public ClasspathPromptLoader(String classpathLocation) {
        this(classpathLocation, new PromptTemplateEngine());
    }

    public ClasspathPromptLoader(String classpathLocation, PromptTemplateEngine engine) {
        this.classpathLocation = classpathLocation == null ? "prompts" : classpathLocation;
        this.engine = engine;
    }

    /**
     * 加载 classpath 下所有提示词模板
     */
    public List<PromptDefinition> load() throws PromptException {
        List<PromptDefinition> result = new ArrayList<>();
        ClassLoader cl = Thread.currentThread().getContextClassLoader();
        if (cl == null) cl = ClasspathPromptLoader.class.getClassLoader();

        java.net.URL baseDir = cl.getResource(classpathLocation);
        if (baseDir == null) {
            return result;
        }

        // 仅支持文件系统形式的 classpath（jar 内资源由 ClassloaderPath 处理）
        if ("file".equals(baseDir.getProtocol())) {
            try {
                Path rootPath = Paths.get(baseDir.toURI());
                loadFromDirectory(rootPath, result);
            } catch (Exception e) {
                throw new PromptException("加载 classpath 提示词失败: " + e.getMessage(), e);
            }
        }
        return result;
    }

    /**
     * 从指定目录递归加载提示词
     */
    private void loadFromDirectory(Path rootDir, List<PromptDefinition> result) throws IOException {
        if (!Files.isDirectory(rootDir)) return;

        try (DirectoryStream<Path> stream = Files.newDirectoryStream(rootDir)) {
            for (Path entry : stream) {
                if (Files.isDirectory(entry)) {
                    loadFromDirectory(entry, result);
                } else if (entry.getFileName().toString().endsWith(".txt")) {
                    PromptDefinition def = loadFile(rootDir, entry);
                    if (def != null) result.add(def);
                }
            }
        }
    }

    /**
     * 加载单个 .txt 文件为 PromptDefinition
     */
    private PromptDefinition loadFile(Path rootDir, Path file) throws IOException {
        String fileName = file.getFileName().toString();
        // 去掉 .txt 后缀作为 scene / promptId
        String scene = fileName.substring(0, fileName.length() - 4);

        // 推断 providerId：父目录名（_global / _shared 跳过）
        Path parent = file.getParent();
        String providerId = null;
        if (parent != null && !parent.equals(rootDir)) {
            String dirName = parent.getFileName().toString();
            if (!"_global".equals(dirName) && !"_shared".equals(dirName)) {
                providerId = dirName;
            }
        }

        // _shared 目录下的文件不作为独立模板
        if (parent != null && "_shared".equals(parent.getFileName().toString())) {
            return null;
        }

        // _global 目录下的文件 providerId 设为 null
        String content = readFile(file);
        List<String> variables = engine.extractVariables(content);

        PromptDefinition def = new PromptDefinition();
        def.setId(scene);
        def.setProviderId(providerId);
        def.setScene(scene);
        def.setVersion("1.0.0");
        def.setContent(content);
        def.setVariables(variables);
        def.setSource("classpath:" + classpathLocation);
        def.setDescription("自动加载自 " + classpathLocation + "/" + relativePath(rootDir, file));
        return def;
    }

    /**
     * 读取文件内容（UTF-8）
     */
    private String readFile(Path file) throws IOException {
        try (InputStream is = Files.newInputStream(file)) {
            byte[] bytes = is.readAllBytes();
            return new String(bytes, StandardCharsets.UTF_8);
        }
    }

    /**
     * 计算相对路径（仅用于描述展示）
     */
    private String relativePath(Path root, Path file) {
        try {
            return root.relativize(file).toString().replace('\\', '/');
        } catch (Exception e) {
            return file.getFileName().toString();
        }
    }

    /**
     * 读取共享片段内容（供 include 使用）
     */
    public String loadSharedFragment(String fragmentPath) throws PromptException {
        if (fragmentPath == null || fragmentPath.isEmpty()) {
            throw new PromptException("include 路径不能为空");
        }
        // fragmentPath 形如 "shared/format-json.txt" 或 "format-json.txt"
        // 都视为相对于 classpathLocation 下查找
        String fullPath = classpathLocation + "/_shared/" + fragmentPath;
        ClassLoader cl = Thread.currentThread().getContextClassLoader();
        if (cl == null) cl = ClasspathPromptLoader.class.getClassLoader();
        try (InputStream is = cl.getResourceAsStream(fullPath)) {
            if (is == null) {
                throw new PromptException("共享片段不存在: " + fragmentPath);
            }
            byte[] bytes = is.readAllBytes();
            return new String(bytes, StandardCharsets.UTF_8);
        } catch (IOException e) {
            throw new PromptException("读取共享片段失败: " + fragmentPath + " - " + e.getMessage(), e);
        }
    }

    public PromptTemplateEngine getEngine() {
        return engine;
    }

    /** 供 DefaultPromptRegistry 获取 classpath 根目录配置 */
    public String getClasspathLocation() {
        return classpathLocation;
    }
}
