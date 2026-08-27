package de.s42.swapmyaxe.config;

import com.terraformersmc.modmenu.api.ConfigScreenFactory;
import com.terraformersmc.modmenu.api.ModMenuApi;
import de.s42.swapmyaxe.SwapMyAxe;
import net.fabricmc.api.EnvType;
import net.fabricmc.api.Environment;
import net.fabricmc.loader.api.FabricLoader;
import net.minecraft.client.gui.screens.Screen;

import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;

@Environment(EnvType.CLIENT)
public class ModMenuIntegration implements ModMenuApi {

    private static final String CLOTH_CONFIG_MOD_ID = "cloth-config";
    private static final String CONFIG_SCREEN_CLASS = "de.s42.swapmyaxe.config.ConfigScreen";

    @Override
    public ConfigScreenFactory<?> getModConfigScreenFactory() {
        if (!FabricLoader.getInstance().isModLoaded(CLOTH_CONFIG_MOD_ID)) {
            SwapMyAxe.LOGGER.info("Cloth Config is not installed; SwapMyAxe config GUI is disabled.");
            return parent -> parent;
        }
        return this::createConfigScreen;
    }

    private Screen createConfigScreen(Screen parent) {
        try {
            Class<?> configScreenClass = Class.forName(CONFIG_SCREEN_CLASS);
            Object configScreen = configScreenClass.getDeclaredConstructor().newInstance();
            Method buildScreen = configScreenClass.getMethod("buildScreen", Screen.class);
            return (Screen) buildScreen.invoke(configScreen, parent);
        } catch (ClassNotFoundException
                 | NoSuchMethodException
                 | InstantiationException
                 | IllegalAccessException
                 | InvocationTargetException e) {
            SwapMyAxe.LOGGER.error("Failed to open the SwapMyAxe config screen.", e);
            return parent;
        }
    }
}
