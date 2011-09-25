import Image
import os
import StringIO
import time

import gtk
try:
    import sane
    HAS_SANE = True
except ImportError, e:
    HAS_SANE = False

from util import gtk_refresh
from util import image2pixbuf
from util import load_uifile
from util import strip_accents

from aboutdialog import AboutDialog
from doc import ScannedDoc
from page import ScannedPage
from docsearch import DocSearch
from settingswindow import SettingsWindow

class MainWindow:
    WIN_TITLE = "Paperwork"

    def __init__(self, config):
        self.config = config
        self.wTree = load_uifile("mainwindow.glade")

        self.mainWindow = self.wTree.get_object("mainWindow")
        assert(self.mainWindow)
        self.progressBar = self.wTree.get_object("progressbarMainWin")
        self.pageList = self.wTree.get_object("liststorePage")
        self.pageListUI = self.wTree.get_object("treeviewPage")
        self.pageScrollWin = self.wTree.get_object("scrolledwindowPageImg")
        self.pageImg = self.wTree.get_object("imagePageImg")
        self.pageEventBox = self.wTree.get_object("eventboxImg")
        self.pageTxt = self.wTree.get_object("textviewPageTxt")
        self.pageVpaned = self.wTree.get_object("vpanedPage")

        # search
        self.liststoreSuggestion = self.wTree.get_object("liststoreSuggestion")
        self.searchField = self.wTree.get_object("entrySearch")
        self.searchCompletion = gtk.EntryCompletion()
        self.searchCompletion.set_model(self.liststoreSuggestion)
        self.searchCompletion.set_text_column(0)
        self.searchCompletion.set_match_func(lambda x, y, z: True)
        self.searchField.set_completion(self.searchCompletion)
        self.matchListUI = self.wTree.get_object("treeviewMatch")
        self.matchList = self.wTree.get_object("liststoreMatch")
        self.vpanedSearch = self.wTree.get_object("vpanedSearch")
        self.matchButton = self.wTree.get_object("buttonMatch")
        self.pageButton = self.wTree.get_object("buttonPage")

        self.wTree.get_object("menuitemScan").set_sensitive(False)
        self.wTree.get_object("toolbuttonScan").set_sensitive(False)

        self.page_scaled = True
        self.new_document()

        self._connect_signals()
        self.mainWindow.set_visible(True)
        gtk_refresh()
        self._reset_search_vpaned(False)

        self._check_workdir()

        self._show_busy_cursor()
        gtk_refresh()
        try:
            self.progressBar.set_text("Initializing scanner ...");
            self.progressBar.set_fraction(0.0)
            self._find_scanner()
            if self.device != None:
                self._set_scanner_config()
                self.wTree.get_object("menuitemScan").set_sensitive(True)
                self.wTree.get_object("toolbuttonScan").set_sensitive(True)
        finally:
            self.progressBar.set_text("");
            self.progressBar.set_fraction(0.0)
            self._show_normal_cursor()

        self._show_busy_cursor()
        try:
            self.progressBar.set_text("Loading documents ...");
            self.progressBar.set_fraction(0.0)
            self.docsearch = DocSearch(self.config.workdir, self._docsearch_callback)
        finally:
            self.progressBar.set_text("");
            self.progressBar.set_fraction(0.0)
            self._show_normal_cursor()

    def _find_scanner(self):
        self.device = None
        if not HAS_SANE:
            # TODO(Jflesch): i18n/l10n
            msg = "python-imaging-sane not found. Scanning will be disabled."
            dialog = gtk.MessageDialog(parent = None,
                                       flags = gtk.DIALOG_MODAL,
                                       type = gtk.MESSAGE_WARNING,
                                       buttons = gtk.BUTTONS_OK,
                                       message_format = msg)
            dialog.run()
            dialog.destroy()
            return
        self.progressBar.set_text("Initializing sane ...");
        self.progressBar.set_fraction(0.0)
        gtk_refresh()
        sane.init()
    
        devices = []
        while len(devices) == 0:
            self.progressBar.set_text("Looking for a scanner ...");
            self.progressBar.set_fraction(0.2)
            gtk_refresh()
            devices = sane.get_devices()
            if len(devices) == 0:
                msg = "No scanner found (is your scanner turned on ?). Look again ?"
                dialog = gtk.MessageDialog(parent = None,
                                           flags = gtk.DIALOG_MODAL,
                                           type = gtk.MESSAGE_WARNING,
                                           buttons = gtk.BUTTONS_YES_NO,
                                           message_format = msg)
                response = dialog.run()
                dialog.destroy()
                if response == gtk.RESPONSE_NO:
                    return

        print "Will use device '%s'" % (str(devices[0]))
        self.device = sane.open(devices[0][0])

    def _set_scanner_config(self):
        assert(HAS_SANE)
        try:
            self.device.resolution = 300
        except AttributeError, e:
            print "WARNING: Can't set scanner resolution: " + e
        try:
            self.device.mode = 'Color'
        except AttributeError, e:
            print "WARNING: Can't set scanner mode: " + e


    def _docsearch_callback(self, step, progression, total, document=None):
        self.progressBar.set_fraction(float(progression) / total)
        if step == DocSearch.INDEX_STEP_READING:
            self.progressBar.set_text("Reading '" + document + "' ... ") # TODO(Jflesch): i18n/l10n
        elif step == DocSearch.INDEX_STEP_SORTING:
            self.progressBar.set_text("Sorting ... ") # TODO(Jflesch): i18n/l10n
        gtk_refresh()

    def _reset_search_vpaned(self, show_doclist):
        vpaned_height = self.vpanedSearch.get_allocation().height
        if show_doclist:
            button_height = self.pageButton.get_allocation().height
            target_position = (vpaned_height - button_height - 5)
        else:
            button_height = self.matchButton.get_allocation().height
            target_position = (button_height - 5)
        # XXX(Jflesch): the following animation should be time-controlled
        pos = self.vpanedSearch.get_position()
        while (abs(pos - target_position) >= 30):
            if pos > target_position:
                pos -= 15
            else:
                pos += 15
            self.vpanedSearch.set_position(pos)
            gtk_refresh()
        self.vpanedSearch.set_position(target_position)

    def _adapt_search(self, search, suggestion):
        suggestion = strip_accents(suggestion).lower()
        # TODO: i18n/l10n: spaces aren't always the correct word separator
        search = strip_accents(search).lower()
        words = search.split(" ")
        search = ""
        for word in words:
            if search != "":
                search += " "
            if suggestion.startswith(word):
                search += suggestion
            else:
                search += word
        print "Suggestion: %s -> %s" % (suggestion, search)

        self._reset_search_vpaned(True)

        return search

    def _update_results(self, objsrc = None):
        txt = unicode(self.searchField.get_text())
        print "Search: %s" % txt

        suggestions = self.docsearch.get_suggestions(txt.split(" "))
        print "Got %d suggestions" % len(suggestions)
        self.liststoreSuggestion.clear()
        full_suggestions = []
        for suggestion in suggestions:
            full_suggestions.append(self._adapt_search(txt, suggestion))
        full_suggestions.sort()
        for suggestion in full_suggestions:
            self.liststoreSuggestion.append([suggestion])

        documents = self.docsearch.get_documents(txt.split(" "))
        print "Got %d documents" % len(documents)
        self.matchList.clear()
        for document in reversed(documents):
            self.matchList.append([document])

    def _apply_search(self, objsrc = None):
        selectionPath = self.matchListUI.get_selection().get_selected()
        if selectionPath[1] == None:
            print "No document selected. Can't open"
            return False
        selection = selectionPath[0].get_value(selectionPath[1], 0)
        doc = self.docsearch.get_doc(selection)

        print "Showing doc %s" % selection
        self.show_doc(doc)
        self.refresh_page()

        return True

    def _show_busy_cursor(self):
        watch = gtk.gdk.Cursor(gtk.gdk.WATCH)
        self.mainWindow.window.set_cursor(watch)
        gtk_refresh()

    def _show_normal_cursor(self):
        self.mainWindow.window.set_cursor(None)

    def _check_workdir(self):
        try:
            os.stat(self.config.workdir)
        except OSError, e:
            print "Unable to stat dir '%s': %s --> opening dialog settings" % (self.config.workdir, e)
            SettingsWindow(self, self.config)
            return

    def _get_keywords(self):
        txt = unicode(self.searchField.get_text())
        words = txt.split(" ")
        for i in range(0, len(words)):
            words[i] = words[i].strip()
            words[i] = strip_accents(words[i])
        return words

    def _show_page_img(self, page):
        im = page.get_boxed_img(self._get_keywords())
        pixbuf = image2pixbuf(im)

        if self.page_scaled:
            # we strip 30 pixels from the width of scrolled window, because the vertical scrollbar
            # is not included
            # TODO(Jflesch): Figure out a way to get the exact scrollbar width
            wantedWidth = self.pageScrollWin.get_allocation().width - 30;
            if pixbuf.get_width() > wantedWidth:
                ratio = float(wantedWidth) / pixbuf.get_width();
                wantedHeight = int(ratio * pixbuf.get_height())
                self.pageImg.window.set_cursor(gtk.gdk.Cursor(gtk.gdk.HAND1))
            else:
                wantedWidth = pixbuf.get_width()
                wantedHeight = pixbuf.get_height()
                self.pageImg.window.set_cursor(None)
            pixbuf = pixbuf.scale_simple(wantedWidth, wantedHeight, gtk.gdk.INTERP_BILINEAR)
        else:
            self.pageImg.window.set_cursor(gtk.gdk.Cursor(gtk.gdk.HAND1))

        self.pageImg.set_from_pixbuf(pixbuf)
        self.pageImg.show()

    def _show_page_txt(self, page):
        txt = page.get_text()
        self.pageTxt.get_buffer().set_text(txt)

    def _reset_page_vpaned(self):
        # keep the vpane as hidden as possible
        self.pageVpaned.set_position(0)

    def _get_selected_page(self):
        selectionPath = self.pageListUI.get_selection().get_selected()
        if selectionPath[1] == None:
            raise Exception("No page selected yet")
        selection = selectionPath[0].get_value(selectionPath[1], 0)
        page = self.doc.get_page(int(selection[5:])) # TODO(Jflesch): i18n/l10n
        return page

    def _get_current_page(self):
        return self.page

    def _show_page(self, page = None):
        if page == None:
            page = self._get_current_page()

        self.page = page
        self.page_scaled = True

        print "Showing page '%s'" % (page)

        self.pageListUI.get_selection().select_path((page.get_page_nb()-1))
        try:
            self._show_page_img(page)
        except Exception, e:
            print "Unable to show image for '%s': %s" % (page, e)
            self.pageImg.set_from_stock(gtk.STOCK_MISSING_IMAGE, gtk.ICON_SIZE_BUTTON)
        try:
            self._show_page_txt(page)
        except Exception, e:
            print "Unable to show text for doc '%s': %s" % (page, e)
            self.pageTxt.get_buffer().set_text("")

    def _show_selected_page(self, objsrc = None):
        self._show_page(self._get_selected_page())

    def refresh_page(self):
        print "Refreshing main window"
        self._show_page_img(self._get_current_page())
        self._reset_page_vpaned()

    def _change_scale(self, objsrc = None, x = None, y = None):
        print "Changing scaling: %d -> %d" % (self.page_scaled, not self.page_scaled)
        self.page_scaled = not self.page_scaled
        self._show_page_img(self._get_current_page())

    def _scan_callback(self, step, progression, total):
        self.progressBar.set_fraction(float(progression) / total)
        if step == ScannedPage.SCAN_STEP_SCAN:
            self.progressBar.set_text("Scanning ... ") # TODO(Jflesch): i18n/l10n
        elif step == ScannedPage.SCAN_STEP_OCR:
            self.progressBar.set_text("Reading ... ") # TODO(Jflesch): i18n/l10n
        gtk_refresh()

    def _refresh_page_list(self):
        self.pageList.clear()
        for page in range(1, self.doc.get_nb_pages()+1):
            self.pageList.append([ "Page %d" % (page) ]) # TODO: i18n/l10n

    def _scan_next_page(self, objsrc = None):
        assert(self.device)

        self._check_workdir()
    
        self._show_busy_cursor()
        try:
            self.doc.scan_next_page(self.device, self.config.ocrlang, self._scan_callback)
            self._refresh_page_list()
            self._show_page(self.doc.get_page(self.doc.get_nb_pages()))
            self._reset_page_vpaned()
        finally:
            self.progressBar.set_text("");
            self.progressBar.set_fraction(0.0)
            self._show_normal_cursor()

    def _destroy_doc(self, objsrc = None):
        confirm = gtk.MessageDialog(parent = self.mainWindow,
                                    flags = gtk.DIALOG_MODAL | gtk.DIALOG_DESTROY_WITH_PARENT,
                                    type = gtk.MESSAGE_WARNING,
                                    buttons = gtk.BUTTONS_YES_NO,
                                    message_format = "Are you sure ?") # TODO(Jflesch): i18n/l10n
        response = confirm.run()
        confirm.destroy()
        if response != gtk.RESPONSE_YES:
            print "Deletion aborted"
            return
        print "Deleting ..."
        self.doc.destroy()
        self.new_document()
        print "Deleted"

    def _print_doc(self, objsrc = None):
        print_op = gtk.PrintOperation()

        print_settings = gtk.PrintSettings()
        # By default, print context are using 72 dpi, but print_draw_page
        # will change it to 300 dpi --> we have to tell PrintOperation to scale
        print_settings.set_scale(100.0 * (72.0 / 300.0))
        print_op.set_print_settings(print_settings)

        print_op.set_n_pages(self.doc.get_nb_pages())
        # remember: we count pages from 1, they don't
        print_op.set_current_page(self._get_current_page().get_page_nb() - 1)
        print_op.set_use_full_page(True)
        print_op.set_job_name(str(self.doc))
        print_op.set_export_filename(str(self.doc) + ".pdf")
        print_op.set_allow_async(True)
        print_op.connect("draw-page", self.doc.print_page)
        res = print_op.run(gtk.PRINT_OPERATION_ACTION_PRINT_DIALOG, self.mainWindow)

    def _clear_search(self, objsrc = None):
        self.searchField.set_text("")
        self._reset_search_vpaned(False)

    def _connect_signals(self):
        self.mainWindow.connect("destroy", lambda x: self._destroy())
        self.wTree.get_object("menuitemNew").connect("activate", self.new_document)
        self.wTree.get_object("toolbuttonNew").connect("clicked", self.new_document)
        self.wTree.get_object("toolbuttonQuit").connect("clicked", lambda x: self._destroy())
        self.wTree.get_object("menuitemScan").connect("activate", self._scan_next_page)
        self.wTree.get_object("toolbuttonScan").connect("clicked", self._scan_next_page)
        self.wTree.get_object("menuitemDestroy").connect("activate", self._destroy_doc)
        self.wTree.get_object("toolbuttonPrint").connect("clicked", self._print_doc)
        self.wTree.get_object("menuitemPrint").connect("activate", self._print_doc)
        self.wTree.get_object("menuitemQuit").connect("activate", lambda x: self._destroy())
        self.wTree.get_object("menuitemAbout").connect("activate", lambda x: AboutDialog())
        self.wTree.get_object("menuitemSettings").connect("activate", lambda x: SettingsWindow(self, self.config))
        self.wTree.get_object("buttonSearchClear").connect("clicked", self._clear_search)
        self.pageListUI.connect("cursor-changed", self._show_selected_page)
        self.pageEventBox.connect("button-press-event", self._change_scale)
        self.searchField.connect("changed", self._update_results)
        self.matchListUI.connect("cursor-changed", self._apply_search)
        self.pageButton.connect("clicked", lambda x: self._reset_search_vpaned(False))
        self.matchButton.connect("clicked", lambda x: self._reset_search_vpaned(True))

    def _destroy(self):
        self.wTree.get_object("mainWindow").destroy()
        gtk.main_quit()

    def cleanup(self):
        if self.device != None:
            self.device.close()

    def _show_doc(self, doc = None):
        """
        Arguments:
            doc --- doc.ScannedDoc (see docsearch.DocSearch.get_doc())
        """
        if doc != None:
            self.doc = doc
        else:
            assert(self.doc)

        self.mainWindow.set_title(str(self.doc) + " - " + self.WIN_TITLE)
        self._refresh_page_list()
        self.page = self.doc.get_page(1)
        self._show_page(self.page)

    def show_doc(self, doc):
        self._show_doc(doc)
        self._reset_page_vpaned()
        self._reset_search_vpaned(False)

    def new_document(self, objsrc = None):
        self._show_doc(ScannedDoc(self.config.workdir)) # new document

